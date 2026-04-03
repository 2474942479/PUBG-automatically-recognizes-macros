import re
p = r'D:\Pycharm\workspace\PUBG-automatically-recognizes-macros\overlay_hud.py'
c = open(p, encoding='utf-8').read()

new_css = """
QWidget#HudRoot {
    background-color: rgba(0,0,0,100);
    border: none;
    border-radius: 4px;
}
QLabel#GunName { color:#ffffff; font-size:56px; font-weight:normal; }
QLabel#SlotIcon { color:#ffffff; font-size:36px; min-width:40px; max-width:40px; }
QLabel#SlotName { color:#ffffff; font-size:32px; min-width:60px; max-width:60px; }
QLabel#SlotVal  { color:#ffffff; font-size:40px; font-weight:normal; }
QLabel#Status   { color:#ffffff; font-size:32px; }
QLabel#Hint     { color:#aaaaaa; font-size:26px; }
QLabel#SlotTag  { color:#ffffff; font-size:30px; font-weight:bold; }
"""

c = re.sub(r'HUD_CSS = """.*?"""', 'HUD_CSS = """' + new_css + '"""', c, flags=re.DOTALL)
open(p, 'w', encoding='utf-8').write(c)
print('OK', len(c))
