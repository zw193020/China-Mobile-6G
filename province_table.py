# -*- coding: utf-8 -*-
"""省份元数据（官网资费专区 31 省代码表，与 tariffZonePers.js 内置表一致）
prov_code 为 getTariffListInfo 接口 province 参数取值；section 为展示站板块标识。
quanguo（全网资费）为独立板块，不在本表。
"""
PROVINCES = [
    # (section, prov_code, 省份名)
    ("beijing",     "100", "北京"),
    ("tianjin",     "220", "天津"),
    ("hebei",       "311", "河北"),
    ("shanxi",      "351", "山西"),
    ("neimenggu",   "471", "内蒙古"),
    ("liaoning",    "240", "辽宁"),
    ("jilin",       "431", "吉林"),
    ("heilongjiang","451", "黑龙江"),
    ("shanghai",    "210", "上海"),
    ("jiangsu",     "250", "江苏"),
    ("zhejiang",    "571", "浙江"),
    ("anhui",       "551", "安徽"),
    ("fujian",      "591", "福建"),
    ("jiangxi",     "791", "江西"),
    ("shandong",    "531", "山东"),
    ("henan",       "371", "河南"),
    ("hubei",       "270", "湖北"),
    ("hunan",       "731", "湖南"),
    ("guangdong",   "200", "广东"),
    ("guangxi",     "771", "广西"),
    ("hainan",      "898", "海南"),
    ("chongqing",   "230", "重庆"),
    ("sichuan",     "280", "四川"),
    ("guizhou",     "851", "贵州"),
    ("yunnan",      "871", "云南"),
    ("xizang",      "891", "西藏"),
    ("shaanxi",     "290", "陕西"),
    ("gansu",       "931", "甘肃"),
    ("qinghai",     "971", "青海"),
    ("ningxia",     "951", "宁夏"),
    ("xinjiang",    "991", "新疆"),
]

# section -> (prov_code, 省份名)
SECTION_INFO = {sec: (code, name) for sec, code, name in PROVINCES}

# 默认监控板块：全网 + 湖南（其它省快照入库后由 build 自动收录展示）
DEFAULT_SECTIONS = ["quanguo", "hunan"]


def section_name(section: str) -> str:
    """板块显示名：quanguo -> 全网；省份 -> 中文省名"""
    if section == "quanguo":
        return "全网(全国)"
    info = SECTION_INFO.get(section)
    return info[1] if info else section
