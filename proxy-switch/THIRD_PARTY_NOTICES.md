# 第三方组件

本工具的原创代码使用根目录 MIT 许可证。下列组件保留各自版权与许可证。

## js-yaml 5.4.1

- 项目：https://github.com/nodeca/js-yaml
- 来源：官方 npm 发布包 `https://registry.npmjs.org/js-yaml/-/js-yaml-5.4.1.tgz`
- 原始下载体积：363,158 字节。
- 原始包 SHA-512（Base64）：`28R/k+NAjeuf7+CKlTxWZVExJGwVVLwY06DgEnOMz2gEpfNkDcD7QvyiVPT0xy0XXhU8vHsd4Ot42OOPdJG7dQ==`
- 许可证：[vendor/js-yaml/LICENSE](vendor/js-yaml/LICENSE)。

发布包只使用官方 CommonJS 构建、包元信息和许可证；没有修改解析器源码，不执行包安装脚本。命令行工具及其 argparse 依赖不在本工具的调用范围中。

## Node.js 24.19.0（Windows x64 程序包）

使用 [Node.js 官方 ZIP](https://nodejs.org/download/release/v24.19.0/node-v24.19.0-win-x64.zip) 中未经修改的 node.exe；没有打包 npm、开发头文件和调试符号。完整版权及第三方许可证见 app/runtime/NODE-LICENSE.txt。文件版本及校验值见 runtime.lock.json（源码）和 app/runtime/runtime-manifest.json（程序包）。

## mihomo 1.19.29（Windows x64 程序包）

使用 [上游官方发布](https://github.com/MetaCubeX/mihomo/releases/tag/v1.19.29) 的 amd64-v2 与 amd64-v1 二进制，仅将文件名改为 FlowSwitch.Core.exe / FlowSwitch.Core.Compat.exe，未修改内核代码。它作为独立进程通过命名管道与 FlowSwitch 通信。

mihomo 按 GNU GPL v3 分发，完整许可证见 app/runtime/MIHOMO-LICENSE.txt。对应版本的上游源码（包括 go.mod、go.sum 及构建工作流）随附在 app/runtime/sources/mihomo-v1.19.29-source.zip；[相同版本源码](https://github.com/MetaCubeX/mihomo/tree/v1.19.29) 也可从上游取得。以源码内 .github/workflows/build.yml 为构建说明，Windows/amd64、GOAMD64=v2（标准）或 v1（兼容）、CGO_ENABLED=0、with_gvisor 标签；依赖版本由 go.mod 和 go.sum 指定。重新分发时应保留本说明、许可证和源码获取方式。

FlowSwitch 自身的原创代码保留 MIT 许可证；上述组件分别遵守其许可证。Clash Verge Rev、Upnet、Codex 未捆绑。包内没有用户订阅、配置或凭据。
