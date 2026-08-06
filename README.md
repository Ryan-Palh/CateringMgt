# 餐饮综合管理系统 v5.0

## 项目结构

```
CCC/
├── desktop/          # 桌面端 (PyQt5)
│   ├── main.py                    # 入口文件
│   ├── build_exe.py               # PyInstaller 打包脚本
│   ├── requirements.txt           # Python 依赖
│   ├── config.ini                 # 坚果云凭据配置
│   ├── assets/                    # 图标资源
│   ├── gui/                       # 19个GUI模块
│   │   ├── main_window.py         # 主窗口(15模块导航)
│   │   ├── login_dialog.py        # 登录对话框
│   │   ├── theme.py               # 餐饮暖色主题系统
│   │   ├── dashboard.py           # 工作台
│   │   ├── revenue.py             # 营业额录入
│   │   ├── revenue_config.py      # 营业额配置
│   │   ├── purchase.py            # 进销存管理(6Tab)
│   │   ├── table_mgt.py           # 桌台管理
│   │   ├── finance.py             # 收支管理
│   │   ├── employee.py            # 员工管理
│   │   ├── shift_mgt.py           # 排班管理
│   │   ├── attendance.py          # 考勤管理
│   │   ├── salary.py              # 工资管理
│   │   ├── reimbursement.py       # 报销管理
│   │   ├── approval.py            # 审批中心
│   │   ├── cost_calc.py           # 成本核算
│   │   ├── report_center.py       # 报表中心
│   │   ├── store_manager.py       # 门店管理
│   │   ├── authorization.py       # 授权管理
│   │   └── calendar_widget.py     # 日历控件
│   ├── database/
│   │   └── db_manager.py          # 数据库管理器
│   ├── utils/                     # 11个工具模块
│   │   ├── config.py / auth_manager.py / nutstore_sync.py
│   │   ├── app_context.py / font_utils.py / helpers.py
│   │   ├── logger.py / validators.py / location_helper.py
│   │   ├── data_io.py / data_linkage.py
│   └── installer/
│       └── setup.iss              # Inno Setup 安装脚本
│
└── mobile/           # 移动端 (Flutter)
    ├── pubspec.yaml               # Flutter 依赖
    ├── lib/
    │   ├── main.dart              # 入口
    │   ├── api/
    │   │   ├── nutstore_sync.dart # 坚果云WebDAV同步
    │   │   └── local_db.dart      # SQLite本地数据库
    │   ├── models/
    │   │   └── models.dart        # 数据模型
    │   ├── screens/
    │   │   ├── login_screen.dart      # 登录
    │   │   ├── home_screen.dart       # 主页(底部导航)
    │   │   ├── dashboard_screen.dart  # 工作台
    │   │   ├── revenue_screen.dart    # 营业额
    │   │   ├── attendance_screen.dart # 考勤打卡
    │   │   ├── schedule_screen.dart   # 排班查看
    │   │   ├── profile_screen.dart    # 个人中心
    │   │   └── settings_screen.dart   # 同步设置
    │   ├── utils/
    │   │   ├── theme.dart         # 餐饮暖色主题
    │   │   └── app_state.dart     # 全局状态管理
    │   └── widgets/
    │       └── summary_card.dart  # 汇总卡片
    └── analysis_options.yaml
```

## 技术栈

| 端 | 技术 | 说明 |
|---|---|---|
| 桌面端 | PyQt5 + SQLite | 19个GUI模块, PyInstaller打包 |
| 移动端 | Flutter + SQLite | 5个主页面, Provider状态管理 |
| 同步 | 坚果云 WebDAV | 整库SQLite文件同步, 无需后端 |

## 餐饮专业特性

- **暖色主题系统**：暖橙(#E8590C)激发食欲、鲜绿(#2B8A3E)代表新鲜、深咖啡(#2C1810)营造质感
- **餐饮岗位**：店长/厨师长/炒锅/切配/打荷/面点师/传菜员/迎宾/收银员/吧台/采购/保洁/会计
- **班次颜色编码**：早班(绿)/中班(橙)/晚班(蓝)/全天(橙红)/休息(灰)
- **营业额渠道**：美团团购/美团外卖/饿了么/抖音团购/堂食/大众点评
- **工资管理**：个税7级累进、工龄工资、试用期折算、管理岗不享受全勤和工龄
- **成本核算**：菜品配方→成本→毛利/毛利率，月度耗用=上月结存+本月采购-本月结存
- **进销存**：6Tab(上月结存/进货台账/出库管理/供货商进货明细/供货商管理/产品数据)

## 打包方式

### 桌面端
```bash
cd desktop
python build_exe.py
# Inno Setup 编译安装包
ISCC.exe installer\setup.iss
```

### 移动端
```bash
cd mobile
flutter pub get
flutter build apk --release
```
