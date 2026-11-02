# 深度模型用 Depth Anything V2 Small，不用 Large

墙、按深度撒的亮点和摩尔纹效果都依赖单目深度估算。工具起初用 Large，后来换成 Small：在测试图上两者找到的墙相同、亮点权重相关系数 0.97–0.99，而 Small 下载 99 MB 而不是 1.3 GB，CPU 上 2 秒而不是 12 秒，并且是 Apache-2.0；Base 和 Large 是 CC BY-NC 4.0，不能商用（`stocking/depth.py` 开头说明，`.scratch/stocking-texture-tool/spec.md`）。

## Consequences

- 模型随安装文件包分发，README 的「第三方组件」写明它和 Segment Anything ViT-B 都是 Apache-2.0；换回 Large 会改变许可和安装体积。
