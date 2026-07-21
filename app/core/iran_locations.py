"""
ماژول متمرکز داده‌های استان‌ها و شهرهای ایران به همراه مختصات جغرافیایی و الگوریتم‌های پارس هوشمند آدرس
"""

import re
from typing import Any, TypedDict


class LocationCoords(TypedDict):
    lat: float
    lng: float


class CityData(TypedDict):
    name: str
    lat: float
    lng: float


class ProvinceData(TypedDict):
    name: str
    capital: str
    lat: float
    lng: float
    cities: list[CityData]


IRAN_PROVINCES_DATA: list[ProvinceData] = [
    {
        "name": "تهران",
        "capital": "تهران",
        "lat": 35.6892,
        "lng": 51.3890,
        "cities": [
            {"name": "تهران", "lat": 35.6892, "lng": 51.3890},
            {"name": "ری", "lat": 35.5901, "lng": 51.4357},
            {"name": "شمیرانات", "lat": 35.8083, "lng": 51.4283},
            {"name": "اسلامشهر", "lat": 35.5614, "lng": 51.2325},
            {"name": "شهریار", "lat": 35.6597, "lng": 51.0592},
            {"name": "قدس", "lat": 35.7208, "lng": 51.1097},
            {"name": "ملارد", "lat": 35.6667, "lng": 50.9833},
            {"name": "ورامین", "lat": 35.3250, "lng": 51.6492},
            {"name": "پاکدشت", "lat": 35.4817, "lng": 51.6803},
            {"name": "دماوند", "lat": 35.7178, "lng": 52.0650},
            {"name": "رباط‌کریم", "lat": 35.4847, "lng": 51.0828},
            {"name": "بهارستان", "lat": 35.5386, "lng": 51.1642},
            {"name": "پردیس", "lat": 35.7360, "lng": 51.8150},
            {"name": "فیروزکوه", "lat": 35.7567, "lng": 52.7719},
        ],
    },
    {
        "name": "اصفهان",
        "capital": "اصفهان",
        "lat": 32.6546,
        "lng": 51.6680,
        "cities": [
            {"name": "اصفهان", "lat": 32.6546, "lng": 51.6680},
            {"name": "کاشان", "lat": 33.9850, "lng": 51.4100},
            {"name": "خمینی‌شهر", "lat": 32.6844, "lng": 51.5361},
            {"name": "نجف‌آباد", "lat": 32.6339, "lng": 51.3486},
            {"name": "شاهین‌شهر", "lat": 32.8625, "lng": 51.5492},
            {"name": "شهرضا", "lat": 32.0089, "lng": 51.8711},
            {"name": "لنجان", "lat": 32.4333, "lng": 51.3167},
            {"name": "فلاورجان", "lat": 32.5583, "lng": 51.5103},
            {"name": "مبارکه", "lat": 32.3489, "lng": 51.5042},
            {"name": "گلپایگان", "lat": 33.4536, "lng": 50.2883},
            {"name": "آران و بیدگل", "lat": 34.0583, "lng": 51.4833},
            {"name": "نائین", "lat": 32.8600, "lng": 53.0875},
            {"name": "نطنز", "lat": 33.5133, "lng": 51.9167},
            {"name": "اردستان", "lat": 33.3789, "lng": 52.3736},
        ],
    },
    {
        "name": "خراسان رضوی",
        "capital": "مشهد",
        "lat": 36.2972,
        "lng": 59.6067,
        "cities": [
            {"name": "مشهد", "lat": 36.2972, "lng": 59.6067},
            {"name": "نیشابور", "lat": 36.2133, "lng": 58.7958},
            {"name": "سبزوار", "lat": 36.2167, "lng": 57.6833},
            {"name": "تربت حیدریه", "lat": 35.2742, "lng": 59.2194},
            {"name": "قوچان", "lat": 37.1064, "lng": 58.5095},
            {"name": "کاشمر", "lat": 35.2383, "lng": 58.4656},
            {"name": "تربت جام", "lat": 35.2439, "lng": 60.6225},
            {"name": "چناران", "lat": 36.6458, "lng": 59.1211},
            {"name": "تایباد", "lat": 34.7400, "lng": 60.7756},
            {"name": "سرخس", "lat": 36.5442, "lng": 61.1578},
            {"name": "گناباد", "lat": 34.3528, "lng": 58.6836},
            {"name": "خواف", "lat": 34.5767, "lng": 60.1383},
        ],
    },
    {
        "name": "فارس",
        "capital": "شیراز",
        "lat": 29.5918,
        "lng": 52.5837,
        "cities": [
            {"name": "شیراز", "lat": 29.5918, "lng": 52.5837},
            {"name": "مرودشت", "lat": 29.8742, "lng": 52.8025},
            {"name": "جهرم", "lat": 28.5000, "lng": 53.5600},
            {"name": "فسا", "lat": 28.9383, "lng": 53.6486},
            {"name": "کازرون", "lat": 29.6194, "lng": 51.6542},
            {"name": "لارستان", "lat": 27.6833, "lng": 54.3333},
            {"name": "داراب", "lat": 28.7519, "lng": 54.5444},
            {"name": "فیروزآباد", "lat": 28.8439, "lng": 52.5706},
            {"name": "آباده", "lat": 31.1608, "lng": 52.6506},
            {"name": "لامرد", "lat": 27.3342, "lng": 53.1789},
        ],
    },
    {
        "name": "آذربایجان شرقی",
        "capital": "تبریز",
        "lat": 38.0962,
        "lng": 46.2738,
        "cities": [
            {"name": "تبریز", "lat": 38.0962, "lng": 46.2738},
            {"name": "مراغه", "lat": 37.3917, "lng": 46.2394},
            {"name": "مرند", "lat": 38.4286, "lng": 45.7744},
            {"name": "میانه", "lat": 37.4208, "lng": 47.6972},
            {"name": "اهر", "lat": 38.4778, "lng": 47.0694},
            {"name": "بناب", "lat": 37.3403, "lng": 46.0561},
            {"name": "شبستر", "lat": 38.1803, "lng": 45.7028},
            {"name": "سراب", "lat": 37.9408, "lng": 47.5367},
            {"name": "اسکو", "lat": 37.9158, "lng": 46.1242},
        ],
    },
    {
        "name": "خوزستان",
        "capital": "اهواز",
        "lat": 31.3183,
        "lng": 48.6706,
        "cities": [
            {"name": "اهواز", "lat": 31.3183, "lng": 48.6706},
            {"name": "دزفول", "lat": 32.3811, "lng": 48.4058},
            {"name": "آبادان", "lat": 30.3392, "lng": 48.3044},
            {"name": "خرمشهر", "lat": 30.4397, "lng": 48.1794},
            {"name": "اندیمشک", "lat": 32.4600, "lng": 48.3500},
            {"name": "ایذه", "lat": 31.8333, "lng": 49.8667},
            {"name": "شوش", "lat": 32.1942, "lng": 47.2436},
            {"name": "ماهشهر", "lat": 30.5589, "lng": 49.1917},
            {"name": "بهبهان", "lat": 30.5958, "lng": 50.2417},
            {"name": "شوشتر", "lat": 32.0456, "lng": 48.8569},
            {"name": "مسجدسلیمان", "lat": 31.9364, "lng": 49.3039},
        ],
    },
    {
        "name": "البرز",
        "capital": "کرج",
        "lat": 35.8327,
        "lng": 50.9915,
        "cities": [
            {"name": "کرج", "lat": 35.8327, "lng": 50.9915},
            {"name": "هشتگرد", "lat": 35.9628, "lng": 50.6828},
            {"name": "نظرآباد", "lat": 35.9525, "lng": 50.6053},
            {"name": "فردیس", "lat": 35.7236, "lng": 50.9828},
            {"name": "طالقان", "lat": 36.1764, "lng": 50.7633},
            {"name": "اشتهارد", "lat": 35.7239, "lng": 50.3664},
            {"name": "چهارباغ", "lat": 35.8375, "lng": 50.8492},
        ],
    },
    {
        "name": "مازندران",
        "capital": "ساری",
        "lat": 36.5633,
        "lng": 53.0601,
        "cities": [
            {"name": "ساری", "lat": 36.5633, "lng": 53.0601},
            {"name": "بابل", "lat": 36.5508, "lng": 52.6789},
            {"name": "آمل", "lat": 36.4678, "lng": 52.3506},
            {"name": "قائم‌شهر", "lat": 36.4628, "lng": 52.8606},
            {"name": "بهشهر", "lat": 36.6925, "lng": 53.5383},
            {"name": "تنکابن", "lat": 36.8167, "lng": 50.8000},
            {"name": "چالوس", "lat": 36.6550, "lng": 51.4206},
            {"name": "نوشهر", "lat": 36.6492, "lng": 51.4964},
            {"name": "بابلسر", "lat": 36.7022, "lng": 52.6581},
            {"name": "رامسر", "lat": 36.9181, "lng": 50.6728},
        ],
    },
    {
        "name": "گیلان",
        "capital": "رشت",
        "lat": 37.2808,
        "lng": 49.5831,
        "cities": [
            {"name": "رشت", "lat": 37.2808, "lng": 49.5831},
            {"name": "بندر انزلی", "lat": 37.4722, "lng": 49.4622},
            {"name": "لاهیجان", "lat": 37.2000, "lng": 50.0000},
            {"name": "لنگرود", "lat": 37.1903, "lng": 50.1539},
            {"name": "تالش", "lat": 37.8000, "lng": 48.9000},
            {"name": "آستارا", "lat": 38.4244, "lng": 48.8717},
            {"name": "صومعه‌سرا", "lat": 37.3128, "lng": 49.3086},
            {"name": "فومن", "lat": 37.2236, "lng": 49.3136},
            {"name": "رودسر", "lat": 37.1375, "lng": 50.2881},
        ],
    },
    {
        "name": "کرمان",
        "capital": "کرمان",
        "lat": 30.2839,
        "lng": 57.0834,
        "cities": [
            {"name": "کرمان", "lat": 30.2839, "lng": 57.0834},
            {"name": "سیرجان", "lat": 29.4522, "lng": 55.6814},
            {"name": "رفسنجان", "lat": 30.4067, "lng": 55.9939},
            {"name": "جیرفت", "lat": 28.6747, "lng": 57.7403},
            {"name": "بم", "lat": 29.1083, "lng": 58.3583},
            {"name": "زرند", "lat": 30.8128, "lng": 56.5639},
            {"name": "شهربابک", "lat": 30.1167, "lng": 55.1167},
            {"name": "کهنوج", "lat": 27.9514, "lng": 57.7014},
        ],
    },
    {
        "name": "سیستان و بلوچستان",
        "capital": "زاهدان",
        "lat": 29.4963,
        "lng": 60.8629,
        "cities": [
            {"name": "زاهدان", "lat": 29.4963, "lng": 60.8629},
            {"name": "زابل", "lat": 31.0314, "lng": 61.4914},
            {"name": "ایرانشهر", "lat": 27.2025, "lng": 60.6847},
            {"name": "چابهار", "lat": 25.2919, "lng": 60.6433},
            {"name": "خاش", "lat": 28.2211, "lng": 61.2158},
            {"name": "سراوان", "lat": 27.3711, "lng": 62.3342},
            {"name": "نیک‌شهر", "lat": 26.2258, "lng": 60.2142},
        ],
    },
    {
        "name": "آذربایجان غربی",
        "capital": "ارومیه",
        "lat": 37.5527,
        "lng": 45.0761,
        "cities": [
            {"name": "ارومیه", "lat": 37.5527, "lng": 45.0761},
            {"name": "خوی", "lat": 38.5503, "lng": 44.9519},
            {"name": "میاندوآب", "lat": 36.9667, "lng": 46.1000},
            {"name": "مهاباد", "lat": 36.7631, "lng": 45.7219},
            {"name": "بوکان", "lat": 36.5208, "lng": 46.2092},
            {"name": "سلماس", "lat": 38.1972, "lng": 44.7653},
            {"name": "نقده", "lat": 36.9553, "lng": 45.3881},
            {"name": "پیرانشهر", "lat": 36.6964, "lng": 45.1417},
        ],
    },
    {
        "name": "کرمانشاه",
        "capital": "کرمانشاه",
        "lat": 34.3142,
        "lng": 47.0650,
        "cities": [
            {"name": "کرمانشاه", "lat": 34.3142, "lng": 47.0650},
            {"name": "اسلام‌آباد غرب", "lat": 34.1094, "lng": 46.5292},
            {"name": "سرپل ذهاب", "lat": 34.4614, "lng": 45.8625},
            {"name": "سنقر", "lat": 34.7836, "lng": 47.5994},
            {"name": "هرسین", "lat": 34.2722, "lng": 47.5861},
            {"name": "کنگاور", "lat": 34.5044, "lng": 47.9653},
            {"name": "جوانرود", "lat": 34.7961, "lng": 46.4950},
        ],
    },
    {
        "name": "لرستان",
        "capital": "خرم‌آباد",
        "lat": 33.4878,
        "lng": 48.3538,
        "cities": [
            {"name": "خرم‌آباد", "lat": 33.4878, "lng": 48.3538},
            {"name": "بروجرد", "lat": 33.8972, "lng": 48.7514},
            {"name": "دورود", "lat": 33.4939, "lng": 49.0778},
            {"name": "کوهدشت", "lat": 33.5342, "lng": 47.6081},
            {"name": "الیگودرز", "lat": 33.4006, "lng": 49.6944},
            {"name": "نورآباد", "lat": 34.0733, "lng": 47.9725},
            {"name": "الشتر", "lat": 33.8631, "lng": 48.2619},
        ],
    },
    {
        "name": "همدان",
        "capital": "همدان",
        "lat": 34.7984,
        "lng": 48.5146,
        "cities": [
            {"name": "همدان", "lat": 34.7984, "lng": 48.5146},
            {"name": "ملایر", "lat": 34.2981, "lng": 48.8242},
            {"name": "نهاوند", "lat": 34.1886, "lng": 48.3756},
            {"name": "تویسرکان", "lat": 34.5483, "lng": 48.4467},
            {"name": "اسدآباد", "lat": 34.7825, "lng": 48.1189},
            {"name": "کبوترآهنگ", "lat": 35.1683, "lng": 48.3589},
        ],
    },
    {
        "name": "یزد",
        "capital": "یزد",
        "lat": 31.8974,
        "lng": 54.3569,
        "cities": [
            {"name": "یزد", "lat": 31.8974, "lng": 54.3569},
            {"name": "میبد", "lat": 32.2272, "lng": 54.0092},
            {"name": "اردکان", "lat": 32.3100, "lng": 54.0175},
            {"name": "بافق", "lat": 31.6039, "lng": 55.4025},
            {"name": "مهریز", "lat": 31.5858, "lng": 54.4417},
            {"name": "ابرقو", "lat": 31.1292, "lng": 53.2842},
        ],
    },
    {
        "name": "کردستان",
        "capital": "سنندج",
        "lat": 35.3113,
        "lng": 46.9959,
        "cities": [
            {"name": "سنندج", "lat": 35.3113, "lng": 46.9959},
            {"name": "سقز", "lat": 36.2497, "lng": 46.2736},
            {"name": "مریوان", "lat": 35.5261, "lng": 46.1758},
            {"name": "بانه", "lat": 35.9975, "lng": 45.8853},
            {"name": "قروه", "lat": 35.1664, "lng": 47.8047},
            {"name": "بیجار", "lat": 35.8719, "lng": 47.6047},
            {"name": "کامیاران", "lat": 34.7967, "lng": 46.9356},
        ],
    },
    {
        "name": "قم",
        "capital": "قم",
        "lat": 34.6416,
        "lng": 50.8746,
        "cities": [
            {"name": "قم", "lat": 34.6416, "lng": 50.8746},
            {"name": "جعفریه", "lat": 34.7644, "lng": 50.5186},
            {"name": "دستجرد", "lat": 34.5517, "lng": 50.2483},
            {"name": "قنوات", "lat": 34.6853, "lng": 51.0450},
            {"name": "سلفچگان", "lat": 34.4539, "lng": 50.4578},
        ],
    },
    {
        "name": "قزوین",
        "capital": "قزوین",
        "lat": 36.2687,
        "lng": 50.0041,
        "cities": [
            {"name": "قزوین", "lat": 36.2687, "lng": 50.0041},
            {"name": "الوند", "lat": 36.1892, "lng": 50.0639},
            {"name": "تاکستان", "lat": 36.0694, "lng": 49.6958},
            {"name": "آبیک", "lat": 36.0542, "lng": 50.5308},
            {"name": "بوئین‌زهرا", "lat": 35.7669, "lng": 50.0578},
        ],
    },
    {
        "name": "گلستان",
        "capital": "گرگان",
        "lat": 36.8456,
        "lng": 54.4393,
        "cities": [
            {"name": "گرگان", "lat": 36.8456, "lng": 54.4393},
            {"name": "گنبد کاووس", "lat": 37.2500, "lng": 55.1667},
            {"name": "علی‌آباد کتول", "lat": 36.9083, "lng": 54.8689},
            {"name": "بندر ترکمن", "lat": 36.9000, "lng": 54.0700},
            {"name": "کردکوی", "lat": 36.7936, "lng": 54.1108},
            {"name": "آزادشهر", "lat": 37.0864, "lng": 55.1736},
        ],
    },
    {
        "name": "اردبیل",
        "capital": "اردبیل",
        "lat": 38.2514,
        "lng": 48.2973,
        "cities": [
            {"name": "اردبیل", "lat": 38.2514, "lng": 48.2973},
            {"name": "پارس‌آباد", "lat": 39.6483, "lng": 47.9172},
            {"name": "مشگین‌شهر", "lat": 38.3986, "lng": 47.6814},
            {"name": "خلخال", "lat": 37.6189, "lng": 48.5258},
            {"name": "گرمی", "lat": 39.0211, "lng": 48.0800},
        ],
    },
    {
        "name": "مرکزی",
        "capital": "اراک",
        "lat": 34.0954,
        "lng": 49.6913,
        "cities": [
            {"name": "اراک", "lat": 34.0954, "lng": 49.6913},
            {"name": "ساوه", "lat": 35.0214, "lng": 50.3567},
            {"name": "خمین", "lat": 33.6425, "lng": 50.0789},
            {"name": "محلات", "lat": 33.9056, "lng": 50.4578},
            {"name": "دلیجان", "lat": 33.9906, "lng": 50.6839},
            {"name": "زرندیه", "lat": 35.3400, "lng": 50.5600},
        ],
    },
    {
        "name": "زنجان",
        "capital": "زنجان",
        "lat": 36.6736,
        "lng": 48.4787,
        "cities": [
            {"name": "زنجان", "lat": 36.6736, "lng": 48.4787},
            {"name": "ابهر", "lat": 36.1464, "lng": 49.2178},
            {"name": "خرمدره", "lat": 36.2069, "lng": 49.1869},
            {"name": "قیدار", "lat": 36.1219, "lng": 48.5919},
            {"name": "طارم", "lat": 36.9500, "lng": 48.9000},
        ],
    },
    {
        "name": "بوشهر",
        "capital": "بوشهر",
        "lat": 28.9234,
        "lng": 50.8203,
        "cities": [
            {"name": "بوشهر", "lat": 28.9234, "lng": 50.8203},
            {"name": "برازجان", "lat": 29.2667, "lng": 51.2158},
            {"name": "کنگان", "lat": 27.8342, "lng": 52.0628},
            {"name": "گناوه", "lat": 29.5792, "lng": 50.5172},
            {"name": "عسلویه", "lat": 27.4764, "lng": 52.6075},
            {"name": "خورموج", "lat": 28.6542, "lng": 51.3814},
        ],
    },
    {
        "name": "چهارمحال و بختیاری",
        "capital": "شهرکرد",
        "lat": 32.3256,
        "lng": 50.8644,
        "cities": [
            {"name": "شهرکرد", "lat": 32.3256, "lng": 50.8644},
            {"name": "بروجن", "lat": 31.9683, "lng": 51.2900},
            {"name": "لردگان", "lat": 31.5089, "lng": 50.8272},
            {"name": "فارسان", "lat": 32.2575, "lng": 50.5636},
        ],
    },
    {
        "name": "خراسان جنوبی",
        "capital": "بیرجند",
        "lat": 32.8663,
        "lng": 59.2211,
        "cities": [
            {"name": "بیرجند", "lat": 32.8663, "lng": 59.2211},
            {"name": "قائن", "lat": 33.7275, "lng": 59.1844},
            {"name": "فردوس", "lat": 34.0186, "lng": 58.1722},
            {"name": "طبس", "lat": 33.5958, "lng": 56.9244},
        ],
    },
    {
        "name": "خراسان شمالی",
        "capital": "بجنورد",
        "lat": 37.4761,
        "lng": 57.3317,
        "cities": [
            {"name": "بجنورد", "lat": 37.4761, "lng": 57.3317},
            {"name": "شیروان", "lat": 37.3967, "lng": 57.9294},
            {"name": "اسفراین", "lat": 37.0764, "lng": 57.5103},
        ],
    },
    {
        "name": "کهگیلویه و بویراحمد",
        "capital": "یاسوج",
        "lat": 30.6691,
        "lng": 51.5878,
        "cities": [
            {"name": "یاسوج", "lat": 30.6691, "lng": 51.5878},
            {"name": "دوگنبدان", "lat": 30.3586, "lng": 50.7981},
            {"name": "دهدشت", "lat": 30.7947, "lng": 50.5656},
        ],
    },
    {
        "name": "هرمزگان",
        "capital": "بندرعباس",
        "lat": 27.1833,
        "lng": 56.2667,
        "cities": [
            {"name": "بندرعباس", "lat": 27.1833, "lng": 56.2667},
            {"name": "میناب", "lat": 27.1464, "lng": 57.0797},
            {"name": "قشم", "lat": 26.9581, "lng": 56.2719},
            {"name": "کیش", "lat": 26.5378, "lng": 53.9747},
            {"name": "بندرلنکه", "lat": 26.5578, "lng": 54.8806},
            {"name": "جاسک", "lat": 25.6439, "lng": 57.7744},
        ],
    },
    {
        "name": "سمنان",
        "capital": "سمنان",
        "lat": 35.5722,
        "lng": 53.3960,
        "cities": [
            {"name": "سمنان", "lat": 35.5722, "lng": 53.3960},
            {"name": "شاهرود", "lat": 36.4181, "lng": 54.9761},
            {"name": "دامغان", "lat": 36.1683, "lng": 54.3481},
            {"name": "گرمشار", "lat": 35.2183, "lng": 52.3406},
        ],
    },
    {
        "name": "ایلام",
        "capital": "ایلام",
        "lat": 33.6374,
        "lng": 46.4227,
        "cities": [
            {"name": "ایلام", "lat": 33.6374, "lng": 46.4227},
            {"name": "دهلران", "lat": 32.6942, "lng": 47.2678},
            {"name": "ایوان", "lat": 33.8292, "lng": 46.3092},
            {"name": "مهران", "lat": 33.1222, "lng": 46.1647},
        ],
    },
]


def normalize_farsi_text(text: str | None) -> str:
    """نرمالسازی متون فارسی جهت مقایسه و جستجوی استاندارد"""
    if not text:
        return ""
    text = text.strip()
    # تبدیل کاراکترهای عربی به فارسی
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه").replace("أ", "ا").replace("إ", "ا")
    # حذف نیم‌فاصله و فواصل اضافی
    text = re.sub(r"[\u200c\u200b\s]+", " ", text).strip()
    return text


def get_all_provinces() -> list[dict[str, Any]]:
    """دریافت لیست کل استان‌های ایران"""
    return [
        {
            "name": p["name"],
            "capital": p["capital"],
            "lat": p["lat"],
            "lng": p["lng"],
            "cities_count": len(p["cities"]),
        }
        for p in IRAN_PROVINCES_DATA
    ]


def get_cities_by_province(province_name: str) -> list[dict[str, Any]]:
    """دریافت شهرهای یک استان مشخص"""
    norm_province = normalize_farsi_text(province_name)
    for p in IRAN_PROVINCES_DATA:
        if normalize_farsi_text(p["name"]) == norm_province or norm_province in normalize_farsi_text(p["name"]):
            return p["cities"]
    return []


def find_nearest_city_coords(lat: float, lng: float) -> dict[str, Any] | None:
    """پیدا کردن نزدیک‌ترین استان و شهر بر اساس مختصات جغرافیایی (Offline Reverse Geocode Fallback)"""
    best_match: dict[str, Any] | None = None
    min_dist_sq = float("inf")

    for p in IRAN_PROVINCES_DATA:
        for c in p["cities"]:
            dist_sq = (c["lat"] - lat) ** 2 + (c["lng"] - lng) ** 2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                best_match = {
                    "province": p["name"],
                    "city": c["name"],
                    "district": "",
                    "lat": c["lat"],
                    "lng": c["lng"],
                }

    return best_match


def parse_smart_address(address_raw: str) -> dict[str, Any]:
    """
    پارسر هوشمند متون ترکیبی و سرهم آدرس (آدرس‌های تایپ‌شده یا Paste شده)
    ورودی: "تهران، اسلامشهر، منطقه ۵، خیابان اصلی پلاک ۱۲"
    خروجی: {"province": "تهران", "city": "اسلامشهر", "district": "منطقه ۵", "address": "خیابان اصلی پلاک ۱۲", "coordinates": {...}}
    """
    norm_text = normalize_farsi_text(address_raw)
    if not norm_text:
        return {"province": "", "city": "", "district": "", "address": "", "coordinates": None}

    detected_province: str = ""
    detected_city: str = ""
    detected_district: str = ""
    coords: dict[str, float] | None = None

    # ۱. جستجوی نام استان
    for p in IRAN_PROVINCES_DATA:
        p_norm = normalize_farsi_text(p["name"])
        if p_norm in norm_text:
            detected_province = p["name"]
            coords = {"lat": p["lat"], "lng": p["lng"]}
            break

    # ۲. جستجوی نام شهر
    for p in IRAN_PROVINCES_DATA:
        for c in p["cities"]:
            c_norm = normalize_farsi_text(c["name"])
            if c_norm in norm_text:
                detected_city = c["name"]
                if not detected_province:
                    detected_province = p["name"]
                coords = {"lat": c["lat"], "lng": c["lng"]}
                break
        if detected_city:
            break

    # ۳. استخراج منطقه/ناحیه در صورت وجود
    district_match = re.search(r"(منطقه\s*\d+|ناحیه\s*\d+|شهرک\s*[\w\s]+)", norm_text)
    if district_match:
        detected_district = district_match.group(1).strip()

    # ۴. تمیزکاری بقیه متن جهت قرارگیری در فیلد آدرس
    cleaned_address = address_raw
    if detected_province:
        cleaned_address = re.sub(re.escape(detected_province), "", cleaned_address, flags=re.IGNORECASE)
    if detected_city and detected_city != detected_province:
        cleaned_address = re.sub(re.escape(detected_city), "", cleaned_address, flags=re.IGNORECASE)

    # پاکسازی جداکننده‌های ابتدایی
    cleaned_address = re.sub(r"^[\s,،\-–_]+", "", cleaned_address).strip()
    if not cleaned_address and detected_city:
        cleaned_address = f"شهر {detected_city}"

    return {
        "province": detected_province,
        "city": detected_city,
        "district": detected_district,
        "address": cleaned_address,
        "coordinates": coords,
    }
