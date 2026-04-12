----jiao ben hong se bu yong guan , bu ying xiang ya qiang
----jiao ben hong se bu yong guan , bu ying xiang ya qiang
----jiao ben hong se bu yong guan , bu ying xiang ya qiang
----------------------------------------------------------
moshi = 1 ---ya qing mo shi
 
----------------------------------------------------------

all_ratio = 1 ---zong ya qiang xi shu

----------------------------------------------------------
akm_ratio = 1 
m762_ratio = 0.92
g36c_ratio = 0.88
m416_ratio = 0.84
scarl_ratio = 0.94
qbz_ratio = 0.88
aug_ratio = 0.85 
groza_ratio = 0.84 
ace32_ratio = 0.89	
tomas_ratio = 0.83
uzi_ratio = 0.7
ump45_ratio = 1
vector_ratio = 0.9
mp5k_ratio = 0.9
p90_ratio = 1
dp28_ratio = 1
m249_ratio = 0.93
mg3_ratio = 1
js9_ratio = 1.2
vss_ratio = 1.2
famas_ratio = 1
mp9_ratio = 1

mini_ratio = 0.6
sks_ratio = 0.5
MK14_ratio = 0.8
mk47_ratio = 0.35
zidong_ratio = 0.6
dela_ratio = 0.6
qbu_ratio = 0.6
mk12_ratio = 0.6
----------------------------------------------------------
GunRatio = {
    akm_ratio, m762_ratio, g36c_ratio, m416_ratio, scarl_ratio, qbz_ratio,
    aug_ratio, groza_ratio, ace32_ratio, k2_ratio, bizon_ratio, tomas_ratio,
    ump45_ratio, uzi_ratio, vector_ratio, mp5k_ratio, p90_ratio, js9_ratio,
    m249_ratio, mg3_ratio, MK14_ratio, famas_ratio, mp9_ratio, vss_ratio,
    dp28_ratio, mk47_ratio,zidong_ratio,dela_ratio,qbu_ratio,mk12_ratio,mini_ratio,sks_ratio
}
wuqifile = "C:/Program Files/aweapon.lua"
jzfile = "C:/Program Files/ab.lua"
ShieldCode = "Lalt"
mode = 2
round = 0
speed = 2
time1 = 25
time2 = 35
wireless = 1
jz = 1
KaiGuan = "capslock"
luopei = "scrolllock"
offkey = 4
round = 0
speed = 2
autodetect = 1
indexPattern = 1
indexWeapon = ""
temp = 0
backx = 0
backx1 = 0.00
backy = 0
backy1 = 0.00
backx2 = 0
backy2 = 0
backx3 = 0
backy3 = 0
tsleep = 0.00
tsleep2 = 0
tsleep3 = 0.00
temptime = 0
i = 0
flag = 0
flag2 = 1
timestart = 0
timebegin = 0
timeend = 0
zhan = 1
ratio = 1
pj2 = 1
pj1 = 1
ditu = 1
ratiobj = 1
noweapon = 0
nowxushu = 0
wuqi = ""
weapon1 = ""
lj = 1
dra = 1

EnablePrimaryMouseButtonEvents(true)
function OnEvent(event, arg)

    if (1) then Sleep(3) end
    if (event == "MOUSE_BUTTON_PRESSED" and arg == 1 and autodetect == 1) then
        indexPattern = 1
        dofile(wuqifile)
		dofile(jzfile)
		
        
    end

	wbflag = wuqi:sub(-2, -2)
	
	if(wbflag == "3") then
		all_ratio = 0.9
	end
       
    SCARL_ = {
        SCARL_1220, SCARL_1040, SCARL_2240, SCARL_2220, SCARL_2200, SCARL_2100,
        SCARL_1210, SCARL_1140, SCARL_1120, SCARL_1000, SCARL_2030, SCARL_2130,
        SCARL_2110, SCARL_2040, SCARL_2230, SCARL_2140, SCARL_2000, SCARL_2210,
        SCARL_1130, SCARL_1010, SCARL_1230, SCARL_1100, SCARL_1020, SCARL_1110,
        SCARL_2120, SCARL_1240, SCARL_2010, SCARL_1200, SCARL_2020, SCARL_1030
    }
    M249_ = {M249_1002, M249_2000, M249_1001, M249_2002, M249_1000, M249_2001}
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
    None_1000 = {}
	ZIDONG_ ={ZIDONG}
	DELA_ = {DELA}
	QBU_ = {QBU}
	MK12_ = {MK12}
	MINI_ = {MINI}
	SKS_ = {SKS}
	MK47_={MK47}
	
	
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
    Wpattern = {
        AKM_, M762_, G36C_, M416_, SCARL_, QBZ_, AUG_, Groza_, ACE32_, K2_,
        BIZON_, Thompson_, UMP45_, UZI_, Vector_, MP5K_, P90_, JS9_, M249_,
        MG3_, MK14_, FAMAS_, MP9_, VSS_, DP28_, MK47_, ZIDONG_,DELA_,QBU_,MK12_,MINI_,SKS_,None_
    }
    duiying = {
        "AKM_", "M762_", "G36C_", "M416_", "SCARL_", "QBZ_", "AUG_", "Groza_",
        "ACE32_", "K2_", "BIZON_", "Thompson_", "UMP45_", "UZI_", "Vector_",
        "MP5K_", "P90_", "JS9_", "M249_",
        "MG3_", "MK14_", "FAMAS_","MP9_", "VSS_", "DP28_", "MK47_", "ZIDONG_","DELA_","QBU_","MK12_","MINI_","SKS_","None_"
    }

	if(wuqi == "MK47" or  wuqi == "ZIDONG" or wuqi == "DELA" or wuqi == "QBU" or wuqi == "MK12" or wuqi == "MINI" or wuqi == "SKS" ) then

		nweapon = wuqi .. "_"
		noweapon = findIndex(duiying, nweapon)
		d_weapon = "d_" .. wuqi
		nowxushu = findIndex(_G[d_weapon], wuqi)
	
	else
		lj = 1
		local we = wuqi:find("_")
		if we then weapon1 = wuqi:sub(1, we - 1) end
		nweapon = weapon1 .. "_"
		noweapon = findIndex(duiying, nweapon)
		d_weapon = "d_" .. weapon1
		nowxushu = findIndex(_G[d_weapon], wuqi)
	end
	
    if (zhan ~= 0) then

        if jz == 6 then
            ratiobj = 5.76
        elseif jz == 4 then
            ratiobj = 4
        elseif jz == 3 then
            ratiobj = 2.8
        elseif jz == 2 then
            ratiobj = 1.76
        elseif jz == 1 then
            ratiobj = 1
        else
        end
    else
        ratiobj = 1
    end
	
    if(zhan==97) then 
      dra = 0.7
    else
      dra = 1
    end
    
    if (zhan == 0) then

        ratio_zong = 0.8
    else
        ratio_zong = lj*all_ratio * GunRatio[noweapon] * ratiobj*dra
    end

	
	

    while IsMouseButtonPressed(1) and flag2 == 1 do
        if (indexWeapon == "Ti") then
            click = true
            SetMKeyState(3)
            break
        end
        
        if moshi == 1 then
            if (wuqi ~= "None" and wuqi ~= 0 and flag == 0) then

                if indexPattern < #Wpattern[noweapon][nowxushu] then
                    if indexPattern == 1 then
                        timestart = GetRunningTime()
                    end
                    ymove = math.ceil(ditu*ratio_zong *
                                          Wpattern[noweapon][nowxushu][indexPattern]
                                              .y)
                    MoveMouseRelative(0,
                                      ymove )
                    timestart = timestart +
                                    Wpattern[noweapon][nowxushu][indexPattern].d
                    Sleep3(timestart)
                    indexPattern = indexPattern + 1
                end
            end
        end

        if moshi == 2 then
            if (wuqi ~= "None" and wuqi ~= 0 and flag == 0 and
                IsMouseButtonPressed(3)) then

                if indexPattern < #Wpattern[noweapon][nowxushu] then
                    if indexPattern == 1 then
                        timestart = GetRunningTime()
                    end
                    ymove = math.ceil(ditu*ratio_zong *
                                          Wpattern[noweapon][nowxushu][indexPattern]
                                              .y)
                    MoveMouseRelative(math.random(-1, 1), ymove)
                    timestart = timestart +
                                    Wpattern[noweapon][nowxushu][indexPattern].d
                    Sleep3(timestart)
                    indexPattern = indexPattern + 1
                end
            end
        end

    end

    if (event == "MOUSE_BUTTON_RELEASED" and indexWeapon ~= 0) then
        if (arg == 1) then
            backx2 = math.floor(backx / 40)
            backy2 = math.floor(backy / 40)
            i = 0
            while (i < round and (backx2 ~= 0 or backy2 ~= 0)) do
                tsleep = (150 + 1.1 *
                             math.sqrt(
                                 math.abs(backx) * math.abs(backx) +
                                     math.abs(backy) * math.abs(backy))) / round /
                             speed
                tsleep2 = math.floor(tsleep)
                tsleep3 = tsleep3 + tsleep - tsleep2
                if tsleep3 >= 1 then
                    tsleep3 = tsleep3 - 1
                    tsleep2 = tsleep2 + 1
                end
                Sleep2(tsleep2)
                backx1 = backx1 + backx / 40 - backx2
                backy1 = backy1 + backy / 40 - backy2
                if (backx1 >= 1) then
                    backx1 = backx1 - 1.00
                    backx3 = backx2 + 1
                else
                    backx3 = backx2
                end
                if (backy1 >= 1) then
                    backy1 = backy1 - 1.00
                    backy3 = backy2 + 1
                else
                    backy3 = backy2
                end
                MoveMouseRelative(backx3, backy3)
                i = i + 1
            end
            indexPattern = 1
            backx = 0
            backy = 0
            backx1 = 0.00
            backy1 = 0.00
            tsleep3 = 0.00
            flag2 = 1
        end
    end

end

if (event == "MOUSE_BUTTON_PRESSED") then
    if (arg ~= 1) then
        if (arg == offkey) then
            timeend = GetRunningTime()
            if (timeend - timebegin < 400) then

                autodetect = 1
                ClearLog()
                OutputLogMessage("~\n")
            else

                autodetect = 1
                indexWeapon = 0
                ClearLog()
                OutputLogMessage("~\n")
            end
            timebegin = GetRunningTime()
        end
        Sleep(1)
    end
end

function Sleep2(time)
    start = GetRunningTime()
    while (time + start > GetRunningTime()) do end
end

function Sleep3(time) while (time > GetRunningTime()) do end end

function findIndex(arr, value)
    for i, v in ipairs(arr) do if v == value then return i end end
    return 0
end
