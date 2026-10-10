安装文件包：`install.bat` 用到的全部文件，包括安装工具 uv、Python、所有依赖包和两个模型。不包含代码，代码在[最新版本](https://github.com/silvermoong/stocking-texture-tool/releases/latest)里下载 Source code (zip)，或者在项目首页点 **Code → Download ZIP**。

**正常安装不用手动下载这里的文件。** `install.bat` 会自动从这里下载需要的文件；这里下载失败的，再改从各自的原始来源下载（PyPI、PyTorch、Hugging Face 等）。

**离线安装**（安装的电脑不用联网）：

1. 下载 `stt-deps-1-base.zip`，再按显卡下载一种 PyTorch：
   - NVIDIA 显卡：`stt-deps-1-torch-cuda.zip.001` 和 `stt-deps-1-torch-cuda.zip.002`，两个都要
   - 其他电脑：`stt-deps-1-torch-cpu.zip`
2. 在 `install.bat` 旁边新建一个 `deps` 文件夹，把下载的文件原样放进去。**不用解压，也不要改文件名**，安装程序会自己拼接、校验和解压。
3. 双击 `install.bat`。

---

Install files: everything `install.bat` needs, namely the uv installer, Python, every package and both models. The code isn't included: download Source code (zip) from the [latest release](https://github.com/silvermoong/stocking-texture-tool/releases/latest), or use **Code → Download ZIP** on the project page.

**A normal install doesn't need you to download these.** `install.bat` downloads what it needs from here by itself, and fetches anything that fails from its original source instead (PyPI, PyTorch, Hugging Face and so on).

**To install with no network on the target machine:**

1. Download `stt-deps-1-base.zip`, plus one PyTorch build:
   - NVIDIA card: `stt-deps-1-torch-cuda.zip.001` and `stt-deps-1-torch-cuda.zip.002` (both)
   - any other PC: `stt-deps-1-torch-cpu.zip`
2. Make a folder named `deps` next to `install.bat` and put the downloaded files in it as they are. **Don't unzip or rename them**: the installer joins, checks and unpacks them itself.
3. Double-click `install.bat`.
