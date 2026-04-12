---- 脚本红色部分不用管，不影响压枪
---- 脚本红色部分不用管，不影响压枪
---- 脚本红色部分不用管，不影响压枪
----------------------------------------------------------
-- 【压枪模式】
-- moshi=1: 模式1 - 按住左键即压枪（无需右键开镜）
-- moshi=2: 模式2 - 必须右键开镜+左键才压枪（更安全，不会在腰射时误触）
moshi = 1
----------------------------------------------------------

-- 【总压枪系数】全局压枪强度倍率，1.0=标准，>1加强，<1减弱
-- 所有武器的压枪位移都会乘以这个系数，可用来整体微调压枪力度
all_ratio = 1

----------------------------------------------------------
-- 【各武器独立压枪系数】
-- 每把枪的后坐力大小不同，这个系数用于微调每把枪的压枪力度
-- 数值越大=压枪越强（鼠标下拉越多），数值越小=压枪越弱
-- 这些值通常根据实际测试调整，使弹道尽量集中在一个点
akm_ratio = 1          -- AKM: 7.62mm步枪，后坐力大，系数1.0
m762_ratio = 0.92     -- Beryl M762: 7.62mm步枪，垂直后坐力较大
g36c_ratio = 0.88     -- G36C: 5.56mm步枪，后坐力较小
m416_ratio = 0.84     -- M416: 5.56mm步枪，满配后坐力小，系数较低
scarl_ratio = 0.94    -- SCAR-L: 5.56mm步枪
qbz_ratio = 0.88      -- QBZ-95: 5.56mm步枪
aug_ratio = 0.85      -- AUG: 5.56mm空投步枪
groza_ratio = 0.84    -- Groza: 7.62mm空投步枪
ace32_ratio = 0.89    -- ACE32: 7.62mm步枪
tomas_ratio = 0.83    -- 汤姆逊冲锋枪
uzi_ratio = 0.7       -- UZI: 射速极快，但单发后坐力小
ump45_ratio = 1       -- UMP45: .45口径冲锋枪
vector_ratio = 0.9    -- Vector: 射速极快的冲锋枪
mp5k_ratio = 0.9      -- MP5K: 冲锋枪
p90_ratio = 1         -- P90: 冲锋枪
dp28_ratio = 1        -- DP-28: 轻机枪，弹盘枪
m249_ratio = 0.93     -- M249: 轻机枪
mg3_ratio = 1         -- MG3: 轻机枪
js9_ratio = 1.2       -- JS9: 冲锋枪，后坐力很小需加大系数
vss_ratio = 1.2       -- VSS: 自带消音的特种枪，后坐力小
famas_ratio = 1       -- FAMAS: 突击步枪
mp9_ratio = 1         -- MP9: 冲锋枪

-- 以下为连狙/DMR的压枪系数，通常较低（后坐力恢复慢，不需要拉太多）
mini_ratio = 0.6      -- Mini14: 连狙
sks_ratio = 0.5       -- SKS: 连狙
MK14_ratio = 0.8      -- MK14: 空投连狙，全自动模式后坐力大
mk47_ratio = 0.35     -- MK47 Mutant: 单发/两连发步枪
zidong_ratio = 0.6    -- 自动装填步枪: 连狙
dela_ratio = 0.6      -- 德拉贡诺夫: 连狙
qbu_ratio = 0.6       -- QBU-88: 连狙
mk12_ratio = 0.6      -- MK12: 连狙
----------------------------------------------------------
-- 【武器压枪系数数组】
-- 与下方 Wpattern 和 duiying 数组一一对应
-- 索引顺序: AKM, M762, G36C, M416, SCARL, QBZ, AUG, Groza, ACE32, K2,
--          Bizon, Thompson, UMP45, UZI, Vector, MP5K, P90, JS9,
--          M249, MG3, MK14, FAMAS, MP9, VSS, DP28, MK47,
--          自动装填, 德拉贡诺夫, QBU, MK12, Mini14, SKS
GunRatio = {
    akm_ratio, m762_ratio, g36c_ratio, m416_ratio, scarl_ratio, qbz_ratio,
    aug_ratio, groza_ratio, ace32_ratio, k2_ratio, bizon_ratio, tomas_ratio,
    ump45_ratio, uzi_ratio, vector_ratio, mp5k_ratio, p90_ratio, js9_ratio,
    m249_ratio, mg3_ratio, MK14_ratio, famas_ratio, mp9_ratio, vss_ratio,
    dp28_ratio, mk47_ratio,zidong_ratio,dela_ratio,qbu_ratio,mk12_ratio,mini_ratio,sks_ratio
}
-- 【外部文件路径】
-- 这两个文件由 Python 程序（本项目）实时生成，包含当前武器和倍镜信息
wuqifile = "C:/Program Files/aweapon.lua"  -- 武器配置文件，包含 wuqi 变量（如 "SCARL_1220"）和弹道数据
jzfile = "C:/Program Files/ab.lua"        -- 倍镜文件，包含 jz 变量（倍镜倍数）

ShieldCode = "Lalt"    -- 盾牌键（未使用）
mode = 2               -- 内部模式标记
round = 0              -- 回弹轮数（松开左键后鼠标回正的步数）
speed = 2              -- 回弹速度
time1 = 25             -- 时间参数1
time2 = 35             -- 时间参数2
wireless = 1           -- 无线鼠标标志

-- 【倍镜倍数】由 ab.lua 文件设置，影响压枪补偿的放大倍率
-- 1=机瞄/红点/全息(1x), 2=2倍, 3=3倍, 4=4倍, 6=6倍
jz = 1

KaiGuan = "capslock"   -- 开关按键（大写锁定键）
luopei = "scrolllock"  -- 罗技配对键（滚动锁定键）
offkey = 4             -- 侧键编号（鼠标侧键4，用于双击重置检测）

round = 0              -- 回弹轮数（重复声明）
speed = 2              -- 回弹速度（重复声明）
autodetect = 1         -- 自动检测开关：1=开启自动武器识别，0=关闭

-- 【运行时状态变量】
indexPattern = 1       -- 当前弹道模式索引（第几发子弹的弹道偏移）
indexWeapon = ""       -- 当前武器标识
temp = 0               -- 临时变量

-- 【回弹相关变量】
-- 松开左键后，鼠标需要反向移动回到初始位置（回弹机制）
backx = 0              -- 累计水平回弹量
backx1 = 0.00          -- 水平回弹余数（用于精度补偿）
backy = 0              -- 累计垂直回弹量
backy1 = 0.00          -- 垂直回弹余数
backx2 = 0             -- 单步水平回弹量
backy2 = 0             -- 单步垂直回弹量
backx3 = 0             -- 实际水平回弹移动量（含余数补偿）
backy3 = 0             -- 实际垂直回弹移动量
tsleep = 0.00          -- 回弹延时（浮点）
tsleep2 = 0            -- 回弹延时（整数）
tsleep3 = 0.00         -- 回弹延时累计误差
temptime = 0           -- 临时时间
i = 0                  -- 循环计数器

flag = 0               -- 压枪标志：0=正常压枪，1=暂停压枪
flag2 = 1              -- 开火标志：1=允许压枪循环
timestart = 0          -- 精确计时起点（用于 Sleep3 精确延时）
timebegin = 0          -- 侧键计时起点（用于双击检测）
timeend = 0            -- 侧键计时终点

-- 【姿态变量】
-- zhan: 姿态标识（由 Python 程序设置）
--   0 = 趴下（压枪力度减到0.8）
--   97 = 特殊姿态（压枪力度减到0.7）
--   其他 = 站立/蹲下（正常压枪）
zhan = 1

ratio = 1              -- 临时比率
pj2 = 1                -- 判断2
pj1 = 1                -- 判断1
ditu = 1               -- 地图/场景系数
ratiobj = 1             -- 倍镜系数（根据 jz 计算得出）
noweapon = 0           -- 当前武器在 duiying 数组中的索引
nowxushu = 0           -- 当前配件配置在武器子数组中的索引
wuqi = ""              -- 当前武器全名（如 "SCARL_1220"，由 aweapon.lua 设置）
weapon1 = ""           -- 武器名前缀（如 "SCARL"，不含配件码）
lj = 1                -- 连接/累计标志
dra = 1               -- 蹲下/特殊姿态系数

-- 【启用鼠标主键事件监听】
-- 必须调用，否则无法检测鼠标按键事件
EnablePrimaryMouseButtonEvents(true)

-- 【主事件处理函数】
-- Logitech G HUB 的入口函数，每次鼠标事件都会触发
-- event: 事件类型 ("MOUSE_BUTTON_PRESSED" / "MOUSE_BUTTON_RELEASED")
-- arg: 按键编号 (1=左键, 3=右键, 4=侧键等)
function OnEvent(event, arg)

    -- 每次事件先短暂休眠3ms，防止事件过于频繁
    if (1) then Sleep(3) end

    -- 【左键按下 + 自动检测开启时】→ 重新加载武器数据
    -- 每次开火前从外部文件读取最新的武器和倍镜信息
    -- 这样 Python 程序识别到新武器后，下次开火就能自动切换弹道
    if (event == "MOUSE_BUTTON_PRESSED" and arg == 1 and autodetect == 1) then
        indexPattern = 1          -- 重置弹道索引到第1发
        dofile(wuqifile)          -- 加载武器数据（设置 wuqi 变量和弹道表）
		dofile(jzfile)            -- 加载倍镜数据（设置 jz 变量）
		
        
    end

    -- 【3号武器位检测】
    -- wuqi 倒数第2个字符如果为 "3"，说明手持的是3号位武器（手枪位）
    -- 3号位武器压枪系数整体降低到0.9
	wbflag = wuqi:sub(-2, -2)
	
	if(wbflag == "3") then
		all_ratio = 0.9
	end
       
    -- ================================================================
    -- 【弹道数据表 - 变量引用版】
    -- 这些数组存储的是弹道变量引用（非字符串），由 aweapon.lua 定义
    -- 每个变量如 SCARL_1220 包含该配件组合下的弹道偏移数据
    --
    -- 配件编码规则（4位数字 ABCD）：
    --   A(千位): 瞄准镜组  1=低倍镜(红点/全息/机瞄)  2=高倍镜(2x及以上)
    --   B(百位): 枪口      0=无  1=补偿器  2=消焰器  3=消音器  4=制退器
    --   C(十位): 握把      0=无  1=垂直  2=直角  3=半截式  4=拇指
    --   D(个位): 枪托      0=无  1=战术枪托/托腮板  2=子弹袋
    --
    -- 示例: SCARL_1220 = SCAR-L + 低倍镜 + 消焰器 + 直角握把 + 无枪托
    -- ================================================================
    SCARL_ = {
        SCARL_1220, SCARL_1040, SCARL_2240, SCARL_2220, SCARL_2200, SCARL_2100,
        SCARL_1210, SCARL_1140, SCARL_1120, SCARL_1000, SCARL_2030, SCARL_2130,
        SCARL_2110, SCARL_2040, SCARL_2230, SCARL_2140, SCARL_2000, SCARL_2210,
        SCARL_1130, SCARL_1010, SCARL_1230, SCARL_1100, SCARL_1020, SCARL_1110,
        SCARL_2120, SCARL_1240, SCARL_2010, SCARL_1200, SCARL_2020, SCARL_1030
    }
    -- M249 轻机枪（配件组合较少）
    M249_ = {M249_1002, M249_2000, M249_1001, M249_2002, M249_1000, M249_2001}
    -- M416 突击步枪（配件组合最多，90种配置）
    -- M416可装4个配件：瞄准镜+枪口+握把+枪托，组合非常丰富
    M416_ = {
        M416_2001, M416_1042, M416_2240, M416_1022, M416_2011, M416_1210,
        M416_2200, M416_1131, M416_2102, M416_1202, M416_2100, M416_1010,
        M416_1232, M416_2111, M416_2221, M416_2142, M416_1142, M416_1241,
        M416_2022, M416_1120, M416_2040, M416_2201, M416_1012, M416_1201,
        M416_1230, M416_2140, M416_1231, M416_1041, M416_2132, M416_1032,
        M416_2030, M416_2041, M416_1100, M416_1221, M416_1222, M416_1141,
        M416_1140, M416_2241, M416_1242, M416_1102, M416_2021, M416_2202,
        M416_1112, M416_1030, M416_1001, M416_2110, M416_2012, M416_1040,
        M416_2130, M416_2230, M416_1011, M416_2032, M416_2112, M416_2121,
        M416_2002, M416_1240, M416_1021, M416_2231, M416_1132, M416_1212,
        M416_2122, M416_2211, M416_2000, M416_1020, M416_1220, M416_1122,
        M416_2222, M416_1031, M416_2131, M416_2220, M416_2042, M416_2212,
        M416_1101, M416_1130, M416_1000, M416_1200, M416_1211, M416_1002,
        M416_2031, M416_2232, M416_1121, M416_1110, M416_2101, M416_1111,
        M416_2141, M416_2120, M416_2020, M416_2242, M416_2210, M416_2010
    }
    -- UZI 冲锋枪（只能装枪口和枪托，握把编码位只有0）
    UZI_ = {UZI_1000, UZI_1100, UZI_2000, UZI_1200, UZI_2100, UZI_2200}
    Vector_ = {
        Vector_1210, Vector_1140, Vector_1030, Vector_1120, Vector_1032,
        Vector_1020, Vector_2000, Vector_1221, Vector_2032, Vector_2111,
        Vector_2140, Vector_2002, Vector_1031, Vector_1202, Vector_2220,
        Vector_2042, Vector_1231, Vector_2031, Vector_2020, Vector_2102,
        Vector_1201, Vector_1100, Vector_2212, Vector_1121, Vector_1222,
        Vector_2010, Vector_1111, Vector_1241, Vector_2240, Vector_2101,
        Vector_1110, Vector_1220, Vector_2210, Vector_2012, Vector_1041,
        Vector_1212, Vector_1141, Vector_2122, Vector_2022, Vector_2112,
        Vector_2232, Vector_2242, Vector_2142, Vector_1021, Vector_2011,
        Vector_1200, Vector_2230, Vector_1001, Vector_1101, Vector_2231,
        Vector_1040, Vector_2100, Vector_1211, Vector_1240, Vector_1131,
        Vector_2202, Vector_2132, Vector_1012, Vector_1130, Vector_1122,
        Vector_1132, Vector_2120, Vector_1042, Vector_1112, Vector_1142,
        Vector_2201, Vector_2001, Vector_2030, Vector_1022, Vector_2041,
        Vector_1010, Vector_2021, Vector_2110, Vector_1000, Vector_1232,
        Vector_2141, Vector_1002, Vector_1242, Vector_2222, Vector_2040,
        Vector_2221, Vector_1011, Vector_2241, Vector_2130, Vector_1230,
        Vector_2211, Vector_2131, Vector_2121, Vector_1102, Vector_2200
    }
    ACE32_ = {
        ACE32_1121, ACE32_2221, ACE32_2241, ACE32_2140, ACE32_2040, ACE32_2212,
        ACE32_1202, ACE32_1142, ACE32_2220, ACE32_2102, ACE32_1020, ACE32_2141,
        ACE32_2120, ACE32_1240, ACE32_2211, ACE32_1120, ACE32_2110, ACE32_1041,
        ACE32_1100, ACE32_1140, ACE32_1110, ACE32_1232, ACE32_1031, ACE32_2242,
        ACE32_1001, ACE32_2130, ACE32_1021, ACE32_1111, ACE32_1231, ACE32_1210,
        ACE32_2011, ACE32_2020, ACE32_2041, ACE32_2101, ACE32_1000, ACE32_1010,
        ACE32_1222, ACE32_2202, ACE32_1040, ACE32_2031, ACE32_1132, ACE32_2222,
        ACE32_1230, ACE32_1201, ACE32_2240, ACE32_1032, ACE32_1131, ACE32_1220,
        ACE32_1242, ACE32_2122, ACE32_2021, ACE32_1030, ACE32_1221, ACE32_2022,
        ACE32_1102, ACE32_2112, ACE32_2032, ACE32_2201, ACE32_1122, ACE32_2030,
        ACE32_2000, ACE32_2002, ACE32_2111, ACE32_1011, ACE32_2132, ACE32_2100,
        ACE32_2200, ACE32_2231, ACE32_2121, ACE32_1211, ACE32_2010, ACE32_1112,
        ACE32_1241, ACE32_2142, ACE32_2012, ACE32_1101, ACE32_1022, ACE32_1002,
        ACE32_2230, ACE32_1200, ACE32_2001, ACE32_2232, ACE32_1042, ACE32_1012,
        ACE32_2131, ACE32_1212, ACE32_1130, ACE32_1141, ACE32_2042, ACE32_2210
    }
    MP5K_ = {
        MP5K_2100, MP5K_2000, MP5K_1230, MP5K_2200, MP5K_1100, MP5K_1000,
        MP5K_2210, MP5K_1020, MP5K_1210, MP5K_2140, MP5K_2020, MP5K_1010,
        MP5K_1220, MP5K_1130, MP5K_2030, MP5K_1200, MP5K_2240, MP5K_2220,
        MP5K_1120, MP5K_1140, MP5K_1110, MP5K_2010, MP5K_1240, MP5K_1030,
        MP5K_2130, MP5K_2120, MP5K_2230, MP5K_1040, MP5K_2110, MP5K_2040
    }
    VSS_ = {VSS_1000, VSS_2000}
    M762_ = {
        M762_1100, M762_1210, M762_2230, M762_2210, M762_1110, M762_2200,
        M762_1230, M762_1130, M762_1120, M762_1020, M762_1140, M762_1000,
        M762_1040, M762_2140, M762_2010, M762_2030, M762_2040, M762_2220,
        M762_1200, M762_2000, M762_2100, M762_1030, M762_2240, M762_1220,
        M762_2020, M762_2130, M762_1010, M762_1240, M762_2110, M762_2120
    }
    G36C_ = {
        G36C_1000, G36C_2220, G36C_2030, G36C_1220, G36C_2000, G36C_2100,
        G36C_2120, G36C_2140, G36C_1120, G36C_2020, G36C_1100, G36C_2230,
        G36C_1010, G36C_2110, G36C_1020, G36C_1110, G36C_2200, G36C_2240,
        G36C_2130, G36C_1040, G36C_1030, G36C_2040, G36C_1140, G36C_1200,
        G36C_1130, G36C_1230, G36C_2210, G36C_2010, G36C_1240
    }
    AKM_ = {AKM_1000, AKM_2100, AKM_1200, AKM_1100, AKM_2000, AKM_2200}
    QBZ_ = {
        QBZ_1100, QBZ_2200, QBZ_2220, QBZ_2110, QBZ_1240, QBZ_1020, QBZ_1210,
        QBZ_1000, QBZ_1120, QBZ_2130, QBZ_1140, QBZ_2240, QBZ_2020, QBZ_2000,
        QBZ_1220, QBZ_2140, QBZ_2120, QBZ_1040, QBZ_2030, QBZ_2040, QBZ_1110,
        QBZ_1130, QBZ_2100, QBZ_2210, QBZ_1230, QBZ_2010, QBZ_1010, QBZ_2230,
        QBZ_1200, QBZ_1030
    }
    UMP45_ = {
        UMP45_1200, UMP45_2230, UMP45_1000, UMP45_1210, UMP45_2200, UMP45_2010,
        UMP45_2130, UMP45_1040, UMP45_2220, UMP45_2030, UMP45_1100, UMP45_2120,
        UMP45_1230, UMP45_1110, UMP45_2140, UMP45_2020, UMP45_2110, UMP45_2000,
        UMP45_1010, UMP45_1240, UMP45_1030, UMP45_1220, UMP45_2210, UMP45_2240,
        UMP45_1140, UMP45_2100, UMP45_1130, UMP45_1020, UMP45_1120, UMP45_2040
    }
    AUG_ = {
        AUG_2240, AUG_2140, AUG_1120, AUG_1130, AUG_2230, AUG_2200, AUG_2110,
        AUG_1200, AUG_2100, AUG_1030, AUG_2130, AUG_1240, AUG_1100, AUG_1010,
        AUG_1110, AUG_2220, AUG_1210, AUG_1000, AUG_2020, AUG_2000, AUG_2030,
        AUG_1140, AUG_1220, AUG_1040, AUG_2120, AUG_2210, AUG_1020, AUG_2040,
        AUG_2010, AUG_1230
    }
    P90_ = {P90_2000, P90_1000}
    Thompson_ = {Thompson_1000, Thompson_1040, Thompson_2040, Thompson_2000}
    K2_ = {K2_1100, K2_2100, K2_2200, K2_2000, K2_1000, K2_1200}
    FAMAS_ = {
        FAMAS_1000, FAMAS_2100, FAMAS_1200, FAMAS_2200, FAMAS_1100, FAMAS_2000
    }
    JS9_ = {JS9_1000, JS9_2100, JS9_2000, JS9_2200, JS9_1100, JS9_1200}
    BIZON_ = {
        BIZON_2200, BIZON_2100, BIZON_1200, BIZON_1000, BIZON_2000, BIZON_1100
    }
    MK14_ = {MK14_2000, MK14_2100, MK14_1000, MK14_1200, MK14_1100, MK14_2200}
    MG3_ = {MG3_1000, MG3_2000}
    Groza_ = {Groza_1000, Groza_2000}
    MP9_ = {MP9_1000, MP9_2000}
    DP28_={DP28_1000,DP28_2000}
    -- 无武器（空手）
    None_1000 = {}
    -- 以下连狙/特殊武器只有单一弹道配置（不受配件组合影响）
	ZIDONG_ ={ZIDONG}     -- 自动装填步枪
	DELA_ = {DELA}         -- 德拉贡诺夫
	QBU_ = {QBU}           -- QBU-88
	MK12_ = {MK12}         -- MK12
	MINI_ = {MINI}         -- Mini14
	SKS_ = {SKS}           -- SKS
	MK47_={MK47}           -- MK47 Mutant
	
	
    -- ================================================================
    -- 【弹道数据表 - 字符串索引版】
    -- 与上面的变量引用版一一对应，但存储的是字符串名称
    -- 用途：通过 findIndex 函数查找当前武器配置在数组中的位置（nowxushu）
    -- 例如：wuqi="SCARL_1220" → 在 d_SCARL 中查找 → 得到索引 1
    -- ================================================================
	d_ZIDONG ={"ZIDONG"}
	d_DELA = {"DELA"}
	d_QBU = {"QBU"}
	d_MK12 = {"MK12"}
	d_MINI = {"MINI"}
	d_SKS= {"SKS"}
	d_MK47={"MK47"}
	
	d_DP28={"DP28_1000","DP28_2000"}
    
    d_SCARL = {
        "SCARL_1220", "SCARL_1040", "SCARL_2240", "SCARL_2220", "SCARL_2200",
        "SCARL_2100", "SCARL_1210", "SCARL_1140", "SCARL_1120", "SCARL_1000",
        "SCARL_2030", "SCARL_2130", "SCARL_2110", "SCARL_2040", "SCARL_2230",
        "SCARL_2140", "SCARL_2000", "SCARL_2210", "SCARL_1130", "SCARL_1010",
        "SCARL_1230", "SCARL_1100", "SCARL_1020", "SCARL_1110", "SCARL_2120",
        "SCARL_1240", "SCARL_2010", "SCARL_1200", "SCARL_2020", "SCARL_1030"
    }
    d_M249 = {
        "M249_1002", "M249_2000", "M249_1001", "M249_2002", "M249_1000",
        "M249_2001"
    }
    d_M416 = {
        "M416_2001", "M416_1042", "M416_2240", "M416_1022", "M416_2011",
        "M416_1210", "M416_2200", "M416_1131", "M416_2102", "M416_1202",
        "M416_2100", "M416_1010", "M416_1232", "M416_2111", "M416_2221",
        "M416_2142", "M416_1142", "M416_1241", "M416_2022", "M416_1120",
        "M416_2040", "M416_2201", "M416_1012", "M416_1201", "M416_1230",
        "M416_2140", "M416_1231", "M416_1041", "M416_2132", "M416_1032",
        "M416_2030", "M416_2041", "M416_1100", "M416_1221", "M416_1222",
        "M416_1141", "M416_1140", "M416_2241", "M416_1242", "M416_1102",
        "M416_2021", "M416_2202", "M416_1112", "M416_1030", "M416_1001",
        "M416_2110", "M416_2012", "M416_1040", "M416_2130", "M416_2230",
        "M416_1011", "M416_2032", "M416_2112", "M416_2121", "M416_2002",
        "M416_1240", "M416_1021", "M416_2231", "M416_1132", "M416_1212",
        "M416_2122", "M416_2211", "M416_2000", "M416_1020", "M416_1220",
        "M416_1122", "M416_2222", "M416_1031", "M416_2131", "M416_2220",
        "M416_2042", "M416_2212", "M416_1101", "M416_1130", "M416_1000",
        "M416_1200", "M416_1211", "M416_1002", "M416_2031", "M416_2232",
        "M416_1121", "M416_1110", "M416_2101", "M416_1111", "M416_2141",
        "M416_2120", "M416_2020", "M416_2242", "M416_2210", "M416_2010"
    }
    d_UZI = {
        "UZI_1000", "UZI_1100", "UZI_2000", "UZI_1200", "UZI_2100", "UZI_2200"
    }
    d_Vector = {
        "Vector_1210", "Vector_1140", "Vector_1030", "Vector_1120",
        "Vector_1032", "Vector_1020", "Vector_2000", "Vector_1221",
        "Vector_2032", "Vector_2111", "Vector_2140", "Vector_2002",
        "Vector_1031", "Vector_1202", "Vector_2220", "Vector_2042",
        "Vector_1231", "Vector_2031", "Vector_2020", "Vector_2102",
        "Vector_1201", "Vector_1100", "Vector_2212", "Vector_1121",
        "Vector_1222", "Vector_2010", "Vector_1111", "Vector_1241",
        "Vector_2240", "Vector_2101", "Vector_1110", "Vector_1220",
        "Vector_2210", "Vector_2012", "Vector_1041", "Vector_1212",
        "Vector_1141", "Vector_2122", "Vector_2022", "Vector_2112",
        "Vector_2232", "Vector_2242", "Vector_2142", "Vector_1021",
        "Vector_2011", "Vector_1200", "Vector_2230", "Vector_1001",
        "Vector_1101", "Vector_2231", "Vector_1040", "Vector_2100",
        "Vector_1211", "Vector_1240", "Vector_1131", "Vector_2202",
        "Vector_2132", "Vector_1012", "Vector_1130", "Vector_1122",
        "Vector_1132", "Vector_2120", "Vector_1042", "Vector_1112",
        "Vector_1142", "Vector_2201", "Vector_2001", "Vector_2030",
        "Vector_1022", "Vector_2041", "Vector_1010", "Vector_2021",
        "Vector_2110", "Vector_1000", "Vector_1232", "Vector_2141",
        "Vector_1002", "Vector_1242", "Vector_2222", "Vector_2040",
        "Vector_2221", "Vector_1011", "Vector_2241", "Vector_2130",
        "Vector_1230", "Vector_2211", "Vector_2131", "Vector_2121",
        "Vector_1102", "Vector_2200"
    }
    d_ACE32 = {
        "ACE32_1121", "ACE32_2221", "ACE32_2241", "ACE32_2140", "ACE32_2040",
        "ACE32_2212", "ACE32_1202", "ACE32_1142", "ACE32_2220", "ACE32_2102",
        "ACE32_1020", "ACE32_2141", "ACE32_2120", "ACE32_1240", "ACE32_2211",
        "ACE32_1120", "ACE32_2110", "ACE32_1041", "ACE32_1100", "ACE32_1140",
        "ACE32_1110", "ACE32_1232", "ACE32_1031", "ACE32_2242", "ACE32_1001",
        "ACE32_2130", "ACE32_1021", "ACE32_1111", "ACE32_1231", "ACE32_1210",
        "ACE32_2011", "ACE32_2020", "ACE32_2041", "ACE32_2101", "ACE32_1000",
        "ACE32_1010", "ACE32_1222", "ACE32_2202", "ACE32_1040", "ACE32_2031",
        "ACE32_1132", "ACE32_2222", "ACE32_1230", "ACE32_1201", "ACE32_2240",
        "ACE32_1032", "ACE32_1131", "ACE32_1220", "ACE32_1242", "ACE32_2122",
        "ACE32_2021", "ACE32_1030", "ACE32_1221", "ACE32_2022", "ACE32_1102",
        "ACE32_2112", "ACE32_2032", "ACE32_2201", "ACE32_1122", "ACE32_2030",
        "ACE32_2000", "ACE32_2002", "ACE32_2111", "ACE32_1011", "ACE32_2132",
        "ACE32_2100", "ACE32_2200", "ACE32_2231", "ACE32_2121", "ACE32_1211",
        "ACE32_2010", "ACE32_1112", "ACE32_1241", "ACE32_2142", "ACE32_2012",
        "ACE32_1101", "ACE32_1022", "ACE32_1002", "ACE32_2230", "ACE32_1200",
        "ACE32_2001", "ACE32_2232", "ACE32_1042", "ACE32_1012", "ACE32_2131",
        "ACE32_1212", "ACE32_1130", "ACE32_1141", "ACE32_2042", "ACE32_2210"
    }
    d_MP5K = {
        "MP5K_2100", "MP5K_2000", "MP5K_1230", "MP5K_2200", "MP5K_1100",
        "MP5K_1000", "MP5K_2210", "MP5K_1020", "MP5K_1210", "MP5K_2140",
        "MP5K_2020", "MP5K_1010", "MP5K_1220", "MP5K_1130", "MP5K_2030",
        "MP5K_1200", "MP5K_2240", "MP5K_2220", "MP5K_1120", "MP5K_1140",
        "MP5K_1110", "MP5K_2010", "MP5K_1240", "MP5K_1030", "MP5K_2130",
        "MP5K_2120", "MP5K_2230", "MP5K_1040", "MP5K_2110", "MP5K_2040"
    }
    d_VSS = {"VSS_1000", "VSS_2000"}
    d_M762 = {
        "M762_1100", "M762_1210", "M762_2230", "M762_2210", "M762_1110",
        "M762_2200", "M762_1230", "M762_1130", "M762_1120", "M762_1020",
        "M762_1140", "M762_1000", "M762_1040", "M762_2140", "M762_2010",
        "M762_2030", "M762_2040", "M762_2220", "M762_1200", "M762_2000",
        "M762_2100", "M762_1030", "M762_2240", "M762_1220", "M762_2020",
        "M762_2130", "M762_1010", "M762_1240", "M762_2110", "M762_2120"
    }
    d_G36C = {
        "G36C_1000", "G36C_2220", "G36C_2030", "G36C_1220", "G36C_2000",
        "G36C_2100", "G36C_2120", "G36C_2140", "G36C_1120", "G36C_2020",
        "G36C_1100", "G36C_2230", "G36C_1010", "G36C_2110", "G36C_1020",
        "G36C_1110", "G36C_2200", "G36C_2240", "G36C_2130", "G36C_1040",
        "G36C_1030", "G36C_2040", "G36C_1140", "G36C_1200", "G36C_1130",
        "G36C_1230", "G36C_2210", "G36C_2010", "G36C_1240"
    }
    d_AKM = {
        "AKM_1000", "AKM_2100", "AKM_1200", "AKM_1100", "AKM_2000", "AKM_2200"
    }
    d_QBZ = {
        "QBZ_1100", "QBZ_2200", "QBZ_2220", "QBZ_2110", "QBZ_1240", "QBZ_1020",
        "QBZ_1210", "QBZ_1000", "QBZ_1120", "QBZ_2130", "QBZ_1140", "QBZ_2240",
        "QBZ_2020", "QBZ_2000", "QBZ_1220", "QBZ_2140", "QBZ_2120", "QBZ_1040",
        "QBZ_2030", "QBZ_2040", "QBZ_1110", "QBZ_1130", "QBZ_2100", "QBZ_2210",
        "QBZ_1230", "QBZ_2010", "QBZ_1010", "QBZ_2230", "QBZ_1200", "QBZ_1030"
    }
    d_UMP45 = {
        "UMP45_1200", "UMP45_2230", "UMP45_1000", "UMP45_1210", "UMP45_2200",
        "UMP45_2010", "UMP45_2130", "UMP45_1040", "UMP45_2220", "UMP45_2030",
        "UMP45_1100", "UMP45_2120", "UMP45_1230", "UMP45_1110", "UMP45_2140",
        "UMP45_2020", "UMP45_2110", "UMP45_2000", "UMP45_1010", "UMP45_1240",
        "UMP45_1030", "UMP45_1220", "UMP45_2210", "UMP45_2240", "UMP45_1140",
        "UMP45_2100", "UMP45_1130", "UMP45_1020", "UMP45_1120", "UMP45_2040"
    }
    d_AUG = {
        "AUG_2240", "AUG_2140", "AUG_1120", "AUG_1130", "AUG_2230", "AUG_2200",
        "AUG_2110", "AUG_1200", "AUG_2100", "AUG_1030", "AUG_2130", "AUG_1240",
        "AUG_1100", "AUG_1010", "AUG_1110", "AUG_2220", "AUG_1210", "AUG_1000",
        "AUG_2020", "AUG_2000", "AUG_2030", "AUG_1140", "AUG_1220", "AUG_1040",
        "AUG_2120", "AUG_2210", "AUG_1020", "AUG_2040", "AUG_2010", "AUG_1230"
    }
    d_P90 = {"P90_2000", "P90_1000"}
    d_Thompson = {
        "Thompson_1000", "Thompson_1040", "Thompson_2040", "Thompson_2000"
    }
    d_K2 = {"K2_1100", "K2_2100", "K2_2200", "K2_2000", "K2_1000", "K2_1200"}
    d_FAMAS = {
        "FAMAS_1000", "FAMAS_2100", "FAMAS_1200", "FAMAS_2200", "FAMAS_1100",
        "FAMAS_2000"
    }
    d_JS9 = {
        "JS9_1000", "JS9_2100", "JS9_2000", "JS9_2200", "JS9_1100", "JS9_1200"
    }
    d_BIZON = {
        "BIZON_2200", "BIZON_2100", "BIZON_1200", "BIZON_1000", "BIZON_2000",
        "BIZON_1100"
    }
    d_MK14 = {
        "MK14_2000", "MK14_2100", "MK14_1000", "MK14_1200", "MK14_1100",
        "MK14_2200"
    }
    d_MG3 = {"MG3_1000", "MG3_2000"}
    d_Groza = {"Groza_1000", "Groza_2000"}
    d_MP9 = {"MP9_1000", "MP9_2000"}
    d_None = {"None_1000"}
    -- 【武器弹道模式总表】
    -- 二维数组: Wpattern[武器索引][配件配置索引] = 弹道数据
    -- 弹道数据格式: 每个元素是一个 {y=垂直偏移, d=时间戳} 的表
    -- 顺序与 GunRatio、duiying 数组严格对应
    Wpattern = {
        AKM_, M762_, G36C_, M416_, SCARL_, QBZ_, AUG_, Groza_, ACE32_, K2_,
        BIZON_, Thompson_, UMP45_, UZI_, Vector_, MP5K_, P90_, JS9_, M249_,
        MG3_, MK14_, FAMAS_, MP9_, VSS_, DP28_, MK47_, ZIDONG_,DELA_,QBU_,MK12_,MINI_,SKS_,None_
    }
    -- 【武器名映射表】
    -- 存储每种武器的名称前缀（带下划线），用于查找武器在总表中的索引
    -- 例如: wuqi="SCARL_1220" → 提取 "SCARL_" → 在此表中查找 → 得到索引 5
    duiying = {
        "AKM_", "M762_", "G36C_", "M416_", "SCARL_", "QBZ_", "AUG_", "Groza_",
        "ACE32_", "K2_", "BIZON_", "Thompson_", "UMP45_", "UZI_", "Vector_",
        "MP5K_", "P90_", "JS9_", "M249_",
        "MG3_", "MK14_", "FAMAS_","MP9_", "VSS_", "DP28_", "MK47_", "ZIDONG_","DELA_","QBU_","MK12_","MINI_","SKS_","None_"
    }

    -- ================================================================
    -- 【武器索引查找】
    -- 根据当前武器名称 wuqi，查找它在总表中的位置
    -- 得到两个关键索引:
    --   noweapon: 武器在 duiying/Wpattern 中的索引（哪把枪）
    --   nowxushu: 配件配置在武器子数组中的索引（哪种配件组合）
    -- ================================================================

	-- 连狙/特殊武器处理：这些武器没有配件组合编码，直接用武器名
	if(wuqi == "MK47" or  wuqi == "ZIDONG" or wuqi == "DELA" or wuqi == "QBU" or wuqi == "MK12" or wuqi == "MINI" or wuqi == "SKS" ) then

		nweapon = wuqi .. "_"                        -- 拼接下划线: "MK47_"
		noweapon = findIndex(duiying, nweapon)       -- 在 duiying 中查找武器索引
		d_weapon = "d_" .. wuqi                      -- 拼接查找前缀: "d_MK47"
		nowxushu = findIndex(_G[d_weapon], wuqi)     -- 在字符串数组中查找配置索引
	
	else
		-- 普通武器处理：wuqi 格式为 "SCARL_1220"，需要提取武器前缀
		lj = 1
		local we = wuqi:find("_")                   -- 找到下划线位置
		if we then weapon1 = wuqi:sub(1, we - 1) end -- 提取武器名: "SCARL"
		nweapon = weapon1 .. "_"                      -- 拼接: "SCARL_"
		noweapon = findIndex(duiying, nweapon)        -- 查找武器索引
		d_weapon = "d_" .. weapon1                    -- 拼接: "d_SCARL"
		nowxushu = findIndex(_G[d_weapon], wuqi)      -- 查找配件配置索引
	end
	
    -- ================================================================
    -- 【倍镜系数计算】
    -- 倍镜越高，瞄准视野越小，同样的鼠标位移在屏幕上看起来更大
    -- 所以高倍镜需要更大的压枪移动量
    -- 公式: 倍镜系数 ≈ 倍镜倍数 × 0.96（经验值）
    -- ================================================================
    if (zhan ~= 0) then   -- 非趴下状态才计算倍镜系数

        if jz == 6 then
            ratiobj = 5.76      -- 6倍镜: 6 × 0.96 = 5.76
        elseif jz == 4 then
            ratiobj = 4         -- 4倍镜: 4 × 1.0 = 4
        elseif jz == 3 then
            ratiobj = 2.8       -- 3倍镜: 3 × 0.93 ≈ 2.8
        elseif jz == 2 then
            ratiobj = 1.76      -- 2倍镜: 2 × 0.88 = 1.76
        elseif jz == 1 then
            ratiobj = 1         -- 1倍镜(机瞄/红点/全息): 1x = 1
        else
        end
    else
        ratiobj = 1              -- 趴下状态不使用倍镜系数
    end
	
    -- 【特殊姿态系数】
    -- zhan=97 表示蹲下状态，蹲下后坐力减小，压枪力度也要相应降低
    if(zhan==97) then 
      dra = 0.7               -- 蹲下: 压枪力度降至70%
    else
      dra = 1                 -- 其他姿态: 正常力度
    end
    
    -- ================================================================
    -- 【总压枪系数计算】
    -- 最终压枪位移 = 弹道数据.y × ratio_zong
    -- ratio_zong 综合了所有影响压枪力度的因素:
    --   lj         - 连接/累计标志（通常为1）
    --   all_ratio  - 全局压枪系数
    --   GunRatio   - 武器独立压枪系数
    --   ratiobj    - 倍镜系数
    --   dra        - 姿态系数
    -- ================================================================
    if (zhan == 0) then

        ratio_zong = 0.8     -- 趴下: 总系数固定为0.8（趴下后坐力本身就小）
    else
        ratio_zong = lj*all_ratio * GunRatio[noweapon] * ratiobj*dra
    end

	
	

    -- ================================================================
    -- 【核心压枪循环】
    -- 当左键持续按下且 flag2==1 时循环执行
    -- 每次循环处理一发子弹的压枪位移
    -- ================================================================
    while IsMouseButtonPressed(1) and flag2 == 1 do
        -- 特殊武器检测（"Ti"可能是提把/特殊模式的标记）
        if (indexWeapon == "Ti") then
            click = true
            SetMKeyState(3)
            break
        end
        
        -- ===== 模式1: 无需开镜即可压枪 =====
        if moshi == 1 then
            -- 条件: 有武器 + 未暂停压枪
            if (wuqi ~= "None" and wuqi ~= 0 and flag == 0) then

                -- 检查是否还有弹道数据可执行（未超出弹匣长度）
                if indexPattern < #Wpattern[noweapon][nowxushu] then
                    -- 第一发子弹时记录起始时间
                    if indexPattern == 1 then
                        timestart = GetRunningTime()
                    end
                    -- 计算垂直移动量 = 场景系数 × 总压枪系数 × 弹道数据中的y值
                    -- math.ceil 向上取整，确保至少移动1像素
                    ymove = math.ceil(ditu*ratio_zong *
                                          Wpattern[noweapon][nowxushu][indexPattern]
                                              .y)
                    -- 仅做垂直移动（水平不偏移）
                    MoveMouseRelative(0,
                                      ymove )
                    -- 累加弹道时间戳，得到下一发子弹的精确触发时间
                    timestart = timestart +
                                    Wpattern[noweapon][nowxushu][indexPattern].d
                    -- Sleep3: 精确延时到 timestart 时刻（忙等待，精度极高）
                    Sleep3(timestart)
                    -- 移动到下一发子弹的弹道数据
                    indexPattern = indexPattern + 1
                end
            end
        end

        -- ===== 模式2: 必须开镜(右键)才压枪 =====
        -- 与模式1类似，但额外要求右键按下，且加入水平随机偏移
        if moshi == 2 then
            -- 条件: 有武器 + 未暂停 + 右键按下(开镜)
            if (wuqi ~= "None" and wuqi ~= 0 and flag == 0 and
                IsMouseButtonPressed(3)) then

                if indexPattern < #Wpattern[noweapon][nowxushu] then
                    if indexPattern == 1 then
                        timestart = GetRunningTime()
                    end
                    ymove = math.ceil(ditu*ratio_zong *
                                          Wpattern[noweapon][nowxushu][indexPattern]
                                              .y)
                    -- 水平加入 -1~1 的随机偏移，模拟人手微小抖动，更自然
                    MoveMouseRelative(math.random(-1, 1), ymove)
                    timestart = timestart +
                                    Wpattern[noweapon][nowxushu][indexPattern].d
                    Sleep3(timestart)
                    indexPattern = indexPattern + 1
                end
            end
        end

    end

    -- ================================================================
    -- 【松开左键 - 鼠标回弹机制】
    -- 压枪时鼠标被持续下拉，松开左键后需要反向移动回到原始位置
    -- 否则瞄准点会偏低，影响下次射击
    -- 回弹分40步执行，每步移动总偏移量的1/40，使回弹过程平滑
    -- ================================================================
    if (event == "MOUSE_BUTTON_RELEASED" and indexWeapon ~= 0) then
        if (arg == 1) then
            -- 计算每步回弹量（整数部分）
            backx2 = math.floor(backx / 40)  -- 水平每步回弹
            backy2 = math.floor(backy / 40)  -- 垂直每步回弹
            i = 0
            -- 循环执行回弹
            while (i < round and (backx2 ~= 0 or backy2 ~= 0)) do
                -- 计算回弹延时：基于总偏移距离，距离越大延时越长
                -- 公式: (150 + 1.1 × √(dx²+dy²)) / 轮数 / 速度
                tsleep = (150 + 1.1 *
                             math.sqrt(
                                 math.abs(backx) * math.abs(backx) +
                                     math.abs(backy) * math.abs(backy))) / round /
                             speed
                tsleep2 = math.floor(tsleep)      -- 取整数延时
                tsleep3 = tsleep3 + tsleep - tsleep2  -- 累计小数部分
                -- 当小数累计≥1时，补偿1ms延时
                if tsleep3 >= 1 then
                    tsleep3 = tsleep3 - 1
                    tsleep2 = tsleep2 + 1
                end
                Sleep2(tsleep2)   -- 普通延时（非忙等待，CPU友好）
                -- 累计余数（因为除以40可能有余数）
                backx1 = backx1 + backx / 40 - backx2
                backy1 = backy1 + backy / 40 - backy2
                -- 水平余数补偿：累计≥1时多移1像素
                if (backx1 >= 1) then
                    backx1 = backx1 - 1.00
                    backx3 = backx2 + 1
                else
                    backx3 = backx2
                end
                -- 垂直余数补偿
                if (backy1 >= 1) then
                    backy1 = backy1 - 1.00
                    backy3 = backy2 + 1
                else
                    backy3 = backy2
                end
                -- 执行回弹移动（反向移动鼠标）
                MoveMouseRelative(backx3, backy3)
                i = i + 1
            end
            -- 重置所有状态变量，为下次射击做准备
            indexPattern = 1     -- 弹道索引归位到第1发
            backx = 0            -- 清零累计水平偏移
            backy = 0            -- 清零累计垂直偏移
            backx1 = 0.00        -- 清零水平余数
            backy1 = 0.00        -- 清零垂直余数
            tsleep3 = 0.00       -- 清零延时累计误差
            flag2 = 1            -- 恢复开火标志
        end
    end

end

    -- ================================================================
    -- 【侧键处理 - 双击重置检测】
    -- 按下鼠标侧键(offkey=4)时:
    --   - 如果距上次按下 < 400ms（双击）: 重启自动检测
    --   - 如果距上次按下 ≥ 400ms（单击）: 重启自动检测并重置武器
    -- 这是用户手动触发重新识别武器的方式
    -- ================================================================
if (event == "MOUSE_BUTTON_PRESSED") then
    if (arg ~= 1) then           -- 非左键
        if (arg == offkey) then   -- 侧键4
            timeend = GetRunningTime()
            if (timeend - timebegin < 400) then
                -- 双击: 快速连续按侧键，重新启用自动检测
                autodetect = 1
                ClearLog()
                OutputLogMessage("~\n")
            else
                -- 单击: 重新启用自动检测并重置武器索引
                autodetect = 1
                indexWeapon = 0
                ClearLog()
                OutputLogMessage("~\n")
            end
            timebegin = GetRunningTime()  -- 记录本次按下时间
        end
        Sleep(1)
    end
end

    -- ================================================================
    -- 【辅助函数】
    -- ================================================================

-- Sleep2: 忙等待延时（回弹用）
-- 从当前时间开始等待指定毫秒数
-- 优点: 比系统Sleep精度高  缺点: CPU占用高
function Sleep2(time)
    start = GetRunningTime()
    while (time + start > GetRunningTime()) do end
end

-- Sleep3: 绝对时间延时（压枪用）
-- 等待直到系统运行时间达到指定时刻
-- 这是最精确的延时方式，确保每发子弹之间的间隔与弹道数据完全匹配
-- timestart 每次累加弹道数据中的 .d 值（该子弹的时间戳）
function Sleep3(time) while (time > GetRunningTime()) do end end

-- findIndex: 在数组中查找指定值的索引
-- 返回值: 找到返回索引(1-based)，未找到返回0
-- 用于: 在 duiying 中查找武器索引，在 d_XXX 中查找配件配置索引
function findIndex(arr, value)
    for i, v in ipairs(arr) do if v == value then return i end end
    return 0
end
