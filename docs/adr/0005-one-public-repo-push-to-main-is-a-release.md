# 一个公开仓库，推送 main 就是发布

本项目只有一个仓库、一个远程（GitHub 上的 `silvermoong/stocking-texture-tool`）。开发资料（`.scratch/`、`AGENTS.md`、`docs/agents/`）也在里面，是公开的，但 `.gitattributes` 的 `export-ignore` 把它们排除在 GitHub 的代码 ZIP 之外，`install.bat` 不会把它们复制给用户。用户运行 `install.bat` 时默认会尝试先更新到 GitHub 上最新的 `main`（加 `-NoUpdate` 或连不上 GitHub 时照常安装手上的代码），所以一次推送就是一次发布（6cd983c，`docs/agents/publishing.md`，`.gitattributes`）。

## Considered Options

- **私有开发仓库加单独的公开仓库**：6cd983c 之前是这样（公开树之外另有私有历史）；6cd983c 合成一个仓库，更早的私有历史不进本仓库。合并的动机提交说明没有写（未知）。
- **选定**：一个仓库，开发资料公开但不进代码 ZIP。

## Consequences

- `tools/commit.txt` 靠 `export-subst` 在 ZIP 里写入提交号，`install.ps1` 用它判断要不要更新，所以永远不重写、不强推 `main`：已安装的副本要在历史里找到自己的提交。
- 改依赖时先发布新的安装文件包 `deps-N`，再推送更新后的 `tools/deps.json`；顺序反了，用户会拿到找不到依赖的新代码（README「开发」一节）。
- 公开的开发资料里不能放私人图片和衍生物，见 `docs/agents/publishing.md` 的媒体规则。
