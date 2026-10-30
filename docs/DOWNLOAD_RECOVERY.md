# 录播下载恢复 / Recording download recovery

校园媒体请求直接连接平台，不继承系统代理。仍验证 HTTPS 证书、限制媒体域名、拒绝未知重定向，并保留原有校园鉴权。课程查询与其他软件的代理设置不变。

分片下载失败时先完成其他分片，再进行最多两轮串行补齐；每次传输最多重试三次。权限拒绝、登录失效、取消和不支持的保护方式不会进入分片补齐。重试整节课时按资源标识、文件长度和校验值复用成功分片，仅重新下载缺失或损坏的片段；不复用未完成的 `.part` 文件。

每个课次的 `media/download-errors.json` 最多保存最近 100 条错误，包括时间、资源哈希、错误类型、HTTP 状态及尝试次数。不会保存请求地址、查询参数、Token、请求头、响应正文或异常原文。耗尽重试后的任务提示会显示错误类型或 HTTP 状态及资源哈希前缀。

更新正在运行的旧版本需重启工作台。优先等待活动任务完成，再切换并续传失败任务；不要同时启动两个实例读写同一数据目录。

Campus media requests bypass system proxies while retaining TLS validation, host restrictions and official authorization. Other software and course API proxy settings are unchanged. Failed segments receive up to two sequential recovery rounds after unaffected segments finish; each transfer has at most three attempts. Permission failures and cancellation are not retried by this recovery loop.

Valid cached segments are reused after identity, size and checksum verification. Unfinished partial files are fetched again. Bounded diagnostics record only time, resource hashes, error classes, HTTP status codes and attempt counts, never signed URLs or credentials. Wait for active tasks before restarting an older workbench, and never run two workbenches against the same data directory.
