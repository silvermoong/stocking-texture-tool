# 用户的文件只读，每种导出只做一件事

工具从不改写用户自己的 PSD：spec 写明用户的 PSD 里有智能对象和生成式填充图层，用 Python 改写这种文件有损坏风险。结果都写成新文件，每次导出一个，各有一个用途：成品图、仅丝袜 PNG、仅纹理 PNG、丝袜引导.psd（`.scratch/stocking-texture-tool/spec.md`，`stocking/export.py` 开头说明）。

## Considered Options

- **把纹理页设置也写进丝袜引导.psd 的 XMP，打开时读回**：在 bb5d3c7 做过，随即在 2e80e3a 撤回，理由是「each export keeps its one purpose」：丝袜引导.psd 装完整合成原图图层和引导（部位、走向线、亮点、隔开线），不装纹理页的设置，也不装纹理结果；结果由成品图和仅丝袜 PNG 承载。
- **选定**：导出各管一件事；纹理设置要带走时用预设文件。

## Consequences

- 导出先写到目标旁边的临时文件再移过去，失败时不留半个文件，也不覆盖之前的导出；建议文件名已存在时自动加 (2)、(3)。
