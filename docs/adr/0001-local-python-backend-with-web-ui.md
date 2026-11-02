# 本机单进程 Python 后端做全部图像处理，界面是 Edge 应用窗口里的网页

工具是一个在本机运行的独立程序，而不是 Photoshop 插件：一个 FastAPI 进程持有打开的文档并做全部图像处理，界面是不用打包器的纯 HTML/JS 页面，以 `msedge --app=http://127.0.0.1:<port>` 的应用窗口打开。图像处理全在 Python 里，所以预览和导出出自同一份代码，细节预览里看到的就是导出的像素（`.scratch/stocking-texture-tool/spec.md` 的 Architecture 一节，`stocking/look.py` 开头说明）。

## Considered Options

- **Photoshop 菜单项，直接把结果放进打开的文档**：spec 里列在 Later，没有做。为什么没有作为第一选择，仓库里没有写（未知）。
- **选定**：本机 Python 服务 + 网页界面，结果以导出文件的形式交给 Photoshop（见 ADR-0002）。

## Consequences

- 本机服务对本机所有网页开放端口，所以服务器检查 Host 和 Origin，挡住 DNS rebinding 和其他网站的修改请求（`stocking/server.py`）。
- 启动器会复用正在运行的同版本服务，旧版本服务被要求保存会话后退出（`stocking/__main__.py`）。
