from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import json

import httpx
import pytest

from yanhe_sentinel.download import VODDownloader, DownloadCanceled
from yanhe_sentinel.portal import PortalError
from test_portal import FakePlatform, platform_client, hls_media


class NoDelay:
    def is_set(self):
        return False

    def wait(self, seconds):
        return False


def test_media_ignores_system_proxy_and_keeps_tls(monkeypatch, tmp_path):
    client = platform_client(FakePlatform())
    client.signed_media_url('https://cvideo.yanhekt.cn/fixture/audio.aac')
    original = httpx.Client
    options = []

    def factory(**kwargs):
        options.append(kwargs)
        kwargs['transport'] = httpx.MockTransport(lambda r: httpx.Response(200, content=b'valid'))
        return original(**kwargs)

    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:1')
    monkeypatch.setattr('yanhe_sentinel.download.httpx.Client', factory)
    VODDownloader(client).direct('https://cvideo.yanhekt.cn/fixture/audio.aac', tmp_path/'audio.aac')
    assert options and all(o['trust_env'] is False and o.get('verify', True) is True for o in options)


def test_http_errors_are_actionable_and_diagnostics_contain_no_secrets(tmp_path):
    client = platform_client(FakePlatform())
    client.signed_media_url('https://cvideo.yanhekt.cn/fixture/audio.aac')
    client._transport = httpx.MockTransport(lambda request: httpx.Response(503, content=b'secret-body'))
    downloader = VODDownloader(client, cancel=NoDelay())
    with pytest.raises(PortalError) as caught:
        downloader.direct('https://cvideo.yanhekt.cn/private/recording.aac?secret=secret-query', tmp_path/'audio.aac')
    assert caught.value.kind == 'download' and 'HTTP 503' in str(caught.value)
    raw = (tmp_path/'download-errors.json').read_text('utf-8')
    records = json.loads(raw)
    assert len(records) == 3 and all(r['http_status'] == 503 for r in records)
    for secret in ['secret-body', 'secret-query', 'test-playback-token', 'Xvideo_Token', 'recording.aac', 'https://']:
        assert secret not in raw and secret not in str(caught.value)


def test_one_exhausted_segment_does_not_abort_others_and_only_failed_piece_retries(tmp_path):
    downloader = VODDownloader(None, cancel=NoDelay())
    counts = Counter()

    def file(url, path, *, byte_range=None):
        counts[url] += 1
        if url == 'bad' and counts[url] == 1:
            raise PortalError('ReadTimeout', 'download')
        path.write_bytes(b'complete')

    downloader._file = file
    transfers = [(url, tmp_path/url, None) for url in ['good', 'bad', 'last']]
    with ThreadPoolExecutor(max_workers=2) as executor:
        downloader._segments(transfers, executor)
    assert counts == {'good': 1, 'bad': 2, 'last': 1}
    assert all(path.read_bytes() == b'complete' for _, path, _ in transfers)


def test_download_repairs_are_bounded_and_permission_errors_are_not_retried(tmp_path):
    for kind, expected in [('download', 3), ('permission', 1)]:
        downloader = VODDownloader(None, cancel=NoDelay())
        attempts = []

        def fail(*args, **kwargs):
            attempts.append(1)
            raise PortalError('safe diagnostic', kind)

        downloader._file = fail
        with ThreadPoolExecutor(max_workers=1) as executor:
            with pytest.raises(PortalError) as caught:
                downloader._segments([('bad', tmp_path/'bad', None)], executor)
        assert len(attempts) == expected and caught.value.kind == kind


def test_real_hls_resume_keeps_all_successful_segment_files(hls_media, tmp_path):
    platform = FakePlatform(hls_media)
    client = platform_client(platform)
    recording = client.recording('100', '200', '300')
    downloader = VODDownloader(client, cancel=NoDelay())
    output = tmp_path/'lecture.mp4'
    failed = {'enabled': True}
    original = platform.__call__

    def transport(request):
        if request.url.path.endswith('part-001.ts') and failed['enabled']:
            return httpx.Response(503)
        return original(request)

    client._transport = httpx.MockTransport(transport)
    with pytest.raises(PortalError):
        downloader.video(recording.screen_url, output)
    kept = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in tmp_path.glob('.download/*/segment-*.ts')}
    assert kept and not output.exists()
    failed['enabled'] = False
    downloader.video(recording.screen_url, output)
    assert output.is_file()
    assert all((p.stat().st_mtime_ns, p.read_bytes()) == value for p, value in kept.items())
