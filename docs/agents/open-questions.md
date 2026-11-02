# 待确认的问题

整理领域文档时，仓库里的证据定不下来的问题。确认后把答案写进对应的 ADR 或 `CONTEXT.md`，再删掉这一条。

## 走向线为什么改成只定方向、不定疏密？

- 证据：`.scratch/stocking-texture-tool/spec.md` 里，走向线挤在一起表示透视，会让横纹变密（period 一条）；`stocking/guide_fields.py` 开头说明写明现在 `|grad V| = 1`（`solve_v` 的说明是约等于 1），走向线「never how dense they are (unlike the reference …)」；README 写「线只管方向，不管疏密」。
- 没找到：改动的理由（例如用户难以控制间距，或透视效果不对）。见 ADR-0003。

## 为什么做成独立程序，而不是 Photoshop 插件？

- 证据：spec 的 Later 一节列着「A Photoshop menu entry that runs the tool and places the result in the open document」，没有做；Architecture 一节选了本机 Python 服务加网页界面。
- 没找到：当初不先做 Photoshop 插件的理由，以及这一项是否还在计划里。见 ADR-0001。

## 为什么把私有开发仓库和公开仓库合成一个？

- 证据：6cd983c「Continue from the public history: one repository, one remote」说明了做法和结果，没有说明动机。
- 没找到：合并的原因。见 ADR-0005。

## 安装为什么从「在项目里建 venv、装依赖、下载模型」改成从 GitHub 上的安装文件包安装？

- 证据：spec 的 Install 一条是前一种做法；5891674「Install from the install files package on GitHub, or offline from a downloaded copy」改成现在的做法，README 写明失败时回退到各自的原始来源，并支持离线安装。
- 已知的考虑：`tools/install.ps1` 开头注释写着，GitHub 上的安装文件包「whoever got this code can reach it, and it needs nothing else」，模型的来源 Hugging Face 和 Meta 在中国大陆被屏蔽；文件齐了之后安装本身不联网。
- 没找到：改动的主要原因（未知）。这一项目前没有写 ADR。
