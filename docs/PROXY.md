# Clash 代理

Windows 的构建下载与 Git 推送可显式使用 Clash HTTP/mixed 端口，端口以自己的 Clash 配置为准。例如本次工作机使用 7897：

```powershell
$env:HTTP_PROXY = 'http://127.0.0.1:7897'
$env:HTTPS_PROXY = 'http://127.0.0.1:7897'
$env:NO_PROXY = 'localhost,127.0.0.1,192.168.0.0/16'
git -c http.proxy=http://127.0.0.1:7897 push origin main
```

不同工具对 NO_PROXY 的 CIDR 支持不同。盒子 SSH/SFTP 属于局域网直连，不应被互联网代理劫持；Python 的 HTTP 检查需要给出实际设备地址作为直连例外。

无需把代理订阅、配置里的账户信息或 GitHub token 提交到仓库。仓库可见性与认证信息不由代理配置改变。
