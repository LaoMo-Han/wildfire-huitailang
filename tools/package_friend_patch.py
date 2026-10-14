"""Package a portable overlay for a friend's complete matching client copy."""
import argparse
import hashlib
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
from build_client import PROJECT, SPEC, sha

GUIDE = '''无尽战区 · 灰太狼离线大厅与练习场补丁

1. 先准备完整的 1.0.192 原客户端，复制一份单独使用。
2. 将此 ZIP 的所有内容解压到这份客户端根目录。game、res、bootstrap
   必须与客户端同名目录合并；提示替换时选择替换。
3. 双击 开始游戏.exe（或 start_offline.cmd），等待进入离线大厅。无需 Python 或账号。
   不要启动 game/wf.exe，也不要用旧的官方更新器。

操作：WASD 移动；鼠标转视角；Ctrl 按一次显示光标，再按一次隐藏。
Z 英雄、X 时装、C 语音、V 故事。同一按键再次按下返回大厅。
Esc 在菜单内返回；在大厅弹出退出确认，再按一次 Esc 取消。B 开关背包。
回车打开大厅聊天输入；回车或 Esc 收起，离线不发送到服务器。
大厅不能攻击，滚轮向上拉近、向下拉远；上下视角可转到接近垂直。
练习场滚轮使用英雄原版技能，不缩放镜头。
时装、配饰、染色剂使用本地数据；原英雄适配范围仍然保留。

背包浏览的是此客户端中的全部物品目录，按分类分页加载。
原素材缺少图标的条目会显示原版问号占位图。
鼠标停在道具上显示原版信息。出生点在大厅中央，角色近距离淡化关闭。
右上角设置的画面页可选 60/80/120/144/165/240 FPS 或不限制，点击应用保存。
默认 80 FPS；开启垂直同步时还会受屏幕刷新率限制。切页和切回窗口保留视角。
练习：大厅左上“练习”→“练习场”。Ctrl 切换光标，顶部菜单可点击。
F1 技能说明、F2 进化树、F3 换英雄、F4 换对手、F5 专属技能、F6 连招引导。
Y 激活／停止对手 AI，可选择难度；B 初始化生命、冷却和对手位置。
L 升一级，Shift+L 满级；Shift+B 同时重置装备、等级和金币。
数字 1–5 先选装备类别，再用数字选择分支购买；再次选同类继续升级。
波浪键 ~（反引号键）撤销最近购买／升级；普通出售在 F2 中操作。
顶部“选择地图”切换本地地图，保留装备和金币；Esc 先收起菜单，再确认返回大厅。

此版本用于本地大厅、角色预览和练习场，匹配、账号服务与联机尚未恢复。
入口的基础教学／独立连招教学尚未接入，装备主动技能、特殊效果和消耗品未完整恢复。
尚未逐一验证全部英雄和地图。
首次加载模型或贴图仍可能短暂停顿。

无需复制发件人的档案或日志。自己的选择会保存在
 game/offline_profile.json，删除该文件可重置自己的离线档案。

GitHub：https://github.com/LaoMo-Han/wildfire-huitailang
'''


def package(client, output):
    if sha((client/'game/wf.exe').read_bytes()) != SPEC['patched_wf_sha256']:
        raise ValueError('Unverified game executable')
    if sha((client/'res/entities.bag').read_bytes()) != SPEC['patched_entities_sha256']:
        raise ValueError('Unverified patched archive')
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError('Choose a new patch ZIP name')
    config = ET.parse(client/'game/conf.xml')
    for key, value in {'screen/width':'1280','screen/height':'720','screen/windowed':'1'}.items():
        node = config.find(key)
        if node is not None:
            node.text = value
    files = [Path('game/wf.exe'), Path('res/entities.bag'), Path('launch.exe'), Path('开始游戏.exe'),
             Path('start_offline.cmd'), Path('bootstrap/EditorConf.py')]
    files += [Path('res/editor/client')/path.name for path in (PROJECT/'runtime').glob('*.py')]
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for relative in files:
            archive.write(client/relative, relative.as_posix())
        archive.writestr('game/conf.xml', ET.tostring(config.getroot(), encoding='utf-8', xml_declaration=True))
        archive.writestr('使用说明.txt', GUIDE.encode('utf-8-sig'))
    print('Created: '+str(output))
    print('Size: '+str(output.stat().st_size))
    print('SHA256: '+hashlib.sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package(args.client, args.output)
