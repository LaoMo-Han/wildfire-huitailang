# 英雄列表与本地切换

此阶段复用客户端的 `guis.HeroList.HeroPageList`，保留原头像、翻页按钮与悬停提示。名单来自客户端 `ClientUtils.get_hero_use` 和本地头像资源；不依赖服务器返回账号英雄库存。

点击头像调用现存 `PracticeRoomHelper.instance().change_attacker(hero_type)`。在离线状态下它更新本地 PlayerHero 和人物模型，不向服务器发送切换请求。选择结果写入独立 `game/offline_profile.json`，下一次启动读取该文件。

生成菜单版：

```powershell
python tools/build_client.py --source "C:\你的客户端目录" --output "C:\offline_heroes" --profile heroes
```

对已生成的菜单副本更新脚本：

```powershell
python tools/deploy_runtime.py --client "C:\offline_heroes" --profile heroes
```

必须从 `start_offline.cmd` 启动。CMD 会恢复 `bootstrap/EditorConf.py`；原游戏退出时仍可保存自己的设置，不会再使自动进入大厅的功能消失。

已通过实际画面验证：

- 原头像列表可以在大厅显示。
- 点击头像后，默认英雄 3 切换为英雄 1，人物模型和技能显示同步变化，状态文件记录 `before=3, after=1`，无当前运行错误。
- 正常退出再从 CMD 启动，可以回到离线大厅，所选英雄 1 保留。
- 原来的大地图通过客户端原 `real_set_visible(False)` 收起，避免遮挡菜单和人物。
- 用户使用实体键盘确认 H 可反复打开、收起列表，双击头像可切换，再次打开后仍可继续切换。

键盘菜单快捷键为 H，保留 F6 兼容入口，并添加屏幕上的“英雄 (H)”按钮。H 已由实体键盘实测；F6 未进行实体键盘验证。只在离线状态下处理这两个菜单键，其他按键继续交给原游戏处理。状态与错误只保存在本地 `game/offline_status.json`、`game/offline_bootstrap.log`，这些运行文件不纳入版本库。

当前是离线英雄浏览和切换界面，未还原联网账号的拥有关系、解锁、皮肤、背包、装备或匹配。部分数据条目可能使用客户端自带占位头像；尚未逐一验证全部英雄的模型和动作。
