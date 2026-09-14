# Surge 模块自动同步

这个仓库定时拉取选定上游，将 Loon／Quantumult X 内容通过 Script-Hub 转成 Surge，并按照既定分组生成最终模块。上游没有变化时不会产生提交；任一必要来源获取或转换失败时，本次同步整体失败，不发布残缺合集。

## 最终模块布局

| 输出 | 内容 |
|---|---|
| `MyBlockAds.sgmodule` | MyBlockAds 软件清单中的普通 App，包括萤石云视频；不包含视频类 App |
| `Bilibili.sgmodule` | 哔哩哔哩，使用 Romeo 镜像的 Kelee Loon 插件完整转换 |
| `YouTube.sgmodule` | YouTube，直接使用 Maasea 原生 Surge 模块 |
| `Video.sgmodule` | 优酷、爱奇艺、芒果 TV、腾讯视频 |
| `AlibabaFamily.sgmodule` | 淘宝、淘宝闪购、大麦、飞猪、夸克、闲鱼、阿里云盘、菜鸟、盒马；1688 暂不启用 |
| `ByteDanceFamily.sgmodule` | 抖音与懂车帝共用的 fmz200 字节系完整模块 |
| `MeituanFamily.sgmodule` | 美团、美团外卖、大众点评、小象超市 |
| `Finance.sgmodule` | 支付宝、云闪付、掌上生活、买单吧、银行、富途和币安等已选金融软件 |
| `AdUnion.sgmodule` | 用户明确选择的 zirawell 广告联盟完整模块，作用范围跨 App |
| `MiniProgramAdBlock.sgmodule` | Romeo 提供的 Kelee 微信小程序 Surge 转换版 |
| `VVebo_repair.sgmodule` | Kelee 的 VVebo 用户时间线和“我的页面”修复 |
| 独立模块 | 贴吧、拼多多、小红书、微博、知乎、喜马拉雅、Spotify |

所有最终 `.sgmodule` 都发布在 `Modules/Surge/` 根目录，不再划分模块子目录。模块引用的脚本、远程数据和规则集会完整镜像到 `Modules/Surge/_resources/`，模块内的运行依赖链接全部改为本仓库的公开 GitHub Pages 地址。作者主页、App Store 和图标属于说明性元数据，不是模块运行依赖，因此保持上游原值。

所有最终模块的 Surge 分类统一设置为 `#!category=AdBlock`。

完整软件、作者、格式和 URL 以 [`config/sources.yaml`](config/sources.yaml) 为准。美的美居、阿里巴巴（1688）、网易 BUFF、京东增强和小红书拆分增强目前明确禁用，不会生成空模块。

## 模块订阅链接

点击下方模块名称即可打开安装页，自动唤起 Surge 安装。若浏览器拦截自动跳转，请点击安装页的“打开 Surge 安装”；也可复制“原始订阅链接”到 Surge 的“从 URL 安装模块”。

<!-- MODULE_LINKS_START -->
- [AdUnion.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=AdUnion.sgmodule)
- [AlibabaFamily.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=AlibabaFamily.sgmodule)
- [Bilibili.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=Bilibili.sgmodule)
- [ByteDanceFamily.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=ByteDanceFamily.sgmodule)
- [Finance.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=Finance.sgmodule)
- [MeituanFamily.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=MeituanFamily.sgmodule)
- [MiniProgramAdBlock.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=MiniProgramAdBlock.sgmodule)
- [MyBlockAds.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=MyBlockAds.sgmodule)
- [PinDuoDuo.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=PinDuoDuo.sgmodule)
- [Spotify.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=Spotify.sgmodule)
- [Tieba.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=Tieba.sgmodule)
- [Video.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=Video.sgmodule)
- [VVebo_repair.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=VVebo_repair.sgmodule)
- [Weibo.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=Weibo.sgmodule)
- [XiaoHongShu.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=XiaoHongShu.sgmodule)
- [Ximalaya.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=Ximalaya.sgmodule)
- [YouTube.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=YouTube.sgmodule)
- [Zhihu.sgmodule](https://bytevista.github.io/Surge-Modules/Modules/Surge/install.html?module=Zhihu.sgmodule)
<!-- MODULE_LINKS_END -->

## 上游备选

以下来源用于查找模块替代方案和上游更新信息。选定具体模块后，再将对应的订阅地址、格式和作者填入 `config/sources.yaml`；本列表不参与自动故障切换。

| 来源 | 入口 | 用途 |
|---|---|---|
| 墨鱼 / ddgksf | [Cuttlefish の自留地](https://t.me/ddgksf2021) | 查看脚本发布、更新说明和订阅入口 |
| fmz200 | [wool_scripts 规则列表](https://github.com/fmz200/wool_scripts/blob/main/README-RULE.md) | 查找 Surge、Loon、QuanX、Egern 等格式的规则和模块链接 |

## 同步原则

- 原生 Surge 上游直接使用；Loon 和 Quantumult X 上游只做格式转换。
- Kelee 项目优先读取 Romeo 已完成的 Surge 转换结果；哔哩哔哩使用 Romeo 镜像的 Kelee Loon 插件，由本仓库转换为 Surge。
- 不从不同作者中拼规则，不补写功能，不裁剪所选上游自带的去广告、页面净化或解锁功能。
- 合集按同名 Surge 配置段汇总，仅删除完全相同的活动行；`[MITM]` 的 hostname 机械合并并精确去重。
- 所有运行时依赖都会镜像，包括 JavaScript、Map Local 远程数据和规则集；文件内容不改，只把模块引用替换为本仓库 Pages 地址。
- 拼多多、微博、知乎和高德地图统一读取 Romeo 镜像的 Kelee Surge 成品；高德地图继续并入 `MyBlockAds.sgmodule`。
- Script-Hub 或上游 CDN 临时返回错误时，单项转换会退避重试；整轮仍失败时，工作流等待后再完整重试一次。

## 自动更新流程

```text
GitHub Actions（每小时第 17 分钟）
        ↓
读取 config/sources.yaml
        ↓
带正确 User-Agent 下载上游
        ↓
原生 Surge 直接使用
Loon / QX 交给 Script-Hub 转换
        ↓
镜像全部脚本与运行时资源
        ↓
按 Video / MyBlockAds / 家族模块合并
        ↓
完整性校验
        ↓
有内容变化才 commit 和 push
        ↓
将模块、JS、JSON 和索引页部署到 GitHub Pages
```

工作流位于 [`.github/workflows/sync-surge-modules.yml`](.github/workflows/sync-surge-modules.yml)。也可以在 GitHub 的 Actions 页面手动运行。

## 部署

1. 将仓库内容推送到 GitHub，默认分支建议使用 `main`。
2. 私有仓库需要 GitHub Pro、Team 或 Enterprise；Pages 发布内容将公开，但仓库中的同步脚本和配置仍保持私有。
3. 打开仓库的 **Settings → Pages**，在 **Build and deployment → Source** 中选择 **GitHub Actions**。
4. 在 **Settings → Actions → General → Workflow permissions** 中选择 **Read and write permissions**。
5. 打开 **Actions → Sync Surge Modules → Run workflow**，执行第一次同步。
6. 成功后，在 Pages 首页或 README 中使用自动生成的模块订阅链接。

项目站点通常位于：

```text
https://你的用户名.github.io/仓库名/
```

模块链接通常位于：

```text
https://你的用户名.github.io/仓库名/Modules/Surge/Bilibili.sgmodule
```

工作流会读取 GitHub Pages 提供的实际站点根地址，因此也兼容自定义域名，不需要在配置中写死用户名或仓库名。

若默认分支启用了“禁止直接推送”的保护规则，需要允许 `github-actions[bot]` 推送，或把提交步骤改为创建 Pull Request。

## 本地检查

本地需要 Python 3.11+；完整转换还需要运行 Script-Hub：

```bash
python -m pip install -r requirements.txt
python scripts/validate_modules.py --config-only
python -m unittest discover -s tests -v
python scripts/sync_modules.py --raw-base https://OWNER.github.io/REPOSITORY/Modules/Surge
python scripts/validate_modules.py
python scripts/build_pages.py --modules Modules/Surge --readme README.md --site _site
```

## 使用提醒

VVebo 修复模块的上游说明要求：使用前禁用微博去广告插件，以免冲突。

部分模块启用 MITM，部分完整上游还带会员、画质、倍速或区域解锁。安装前请阅读生成模块顶部的来源列表；遇到登录、支付、播放或页面异常时，应先停用对应合集排查。所有模块及脚本版权归各上游作者，本仓库只负责自动同步、格式转换和组合发布。
