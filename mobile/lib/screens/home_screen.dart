// screens/home_screen.dart — 主页（抽屉式导航，与桌面端15模块完全对齐）
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../utils/theme.dart';
import '../utils/app_state.dart';
import 'dashboard_screen.dart';
import 'revenue_screen.dart';
import 'purchase_screen.dart';
import 'table_screen.dart';
import 'finance_screen.dart';
import 'employee_screen.dart';
import 'schedule_screen.dart';
import 'attendance_screen.dart';
import 'salary_screen.dart';
import 'reimbursement_screen.dart';
import 'approval_screen.dart';
import 'cost_calc_screen.dart';
import 'report_screen.dart';
import 'store_screen.dart';
import 'authorization_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _currentIndex = 0;
  List<Map<String, dynamic>> _stores = [];
  bool _storesLoaded = false;

  final _pages = const [
    DashboardScreen(),
    RevenueScreen(),
    PurchaseScreen(),
    TableScreen(),
    FinanceScreen(),
    EmployeeScreen(),
    ScheduleScreen(),
    AttendanceScreen(),
    SalaryScreen(),
    ReimbursementScreen(),
    ApprovalScreen(),
    CostCalcScreen(),
    ReportScreen(),
    StoreScreen(),
    AuthorizationScreen(),
    SettingsScreen(),
  ];

  // 名称与桌面端NAV_GROUPS完全一致，图标语义对齐桌面端emoji
  final _menuItems = [
    _MenuItem('工作台', Icons.home_outlined, Icons.home),
    _MenuItem('营业额', Icons.bar_chart_outlined, Icons.bar_chart),
    _MenuItem('进销存管理', Icons.inventory_2_outlined, Icons.inventory_2),
    _MenuItem('桌台管理', Icons.table_restaurant_outlined, Icons.table_restaurant),
    _MenuItem('收支管理', Icons.account_balance_wallet_outlined, Icons.account_balance_wallet),
    _MenuItem('员工管理', Icons.people_outlined, Icons.people),
    _MenuItem('排班管理', Icons.calendar_month_outlined, Icons.calendar_month),
    _MenuItem('考勤管理', Icons.access_time_outlined, Icons.access_time),
    _MenuItem('工资管理', Icons.payments_outlined, Icons.payments),
    _MenuItem('报销管理', Icons.receipt_long_outlined, Icons.receipt_long),
    _MenuItem('审批中心', Icons.check_circle_outline, Icons.check_circle),
    _MenuItem('成本核算', Icons.trending_up_outlined, Icons.trending_up),
    _MenuItem('报表中心', Icons.assignment_outlined, Icons.assignment),
    _MenuItem('门店管理', Icons.storefront_outlined, Icons.storefront),
    _MenuItem('授权管理', Icons.lock_outline, Icons.lock),
    _MenuItem('设置', Icons.settings_outlined, Icons.settings),
  ];

  @override
  void initState() {
    super.initState();
    _loadStores();
  }

  Future<void> _loadStores() async {
    final stores = await context.read<AppState>().loadStores();
    if (mounted) {
      setState(() {
        _stores = stores;
        _storesLoaded = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final appState = context.watch<AppState>();
    return Scaffold(
      appBar: AppBar(
        title: Text(_menuItems[_currentIndex].label),
        leading: Builder(
          builder: (context) => IconButton(
            icon: const Icon(Icons.menu),
            onPressed: () => Scaffold.of(context).openDrawer(),
          ),
        ),
        actions: [
          // 门店选择器
          if (_stores.length > 1)
            PopupMenuButton<int>(
              icon: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.storefront, size: 18),
                  const SizedBox(width: 4),
                  Text(appState.storeName, style: const TextStyle(fontSize: 13)),
                ],
              ),
              onSelected: (storeId) {
                if (storeId == 0) {
                  appState.setStore(null, '全部门店');
                } else {
                  final store = _stores.firstWhere((s) => s['id'] == storeId);
                  appState.setStore(storeId, store['name'] as String? ?? '');
                }
                setState(() {});
              },
              itemBuilder: (context) => [
                const PopupMenuItem(value: 0, child: Text('全部门店')),
                ..._stores.map((s) => PopupMenuItem(
                  value: s['id'] as int,
                  child: Text(s['name'] as String? ?? ''),
                )),
              ],
            ),
          IconButton(
            icon: Icon(appState.isSyncing ? Icons.sync : Icons.cloud_sync_outlined),
            onPressed: () async {
              final result = await appState.sync();
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(result), duration: const Duration(seconds: 2)),
                );
              }
            },
          ),
        ],
      ),
      drawer: Drawer(
        child: ListView.builder(
          padding: EdgeInsets.zero,
          itemCount: _menuItems.length + 1,
          itemBuilder: (context, index) {
            if (index == 0) {
              return _buildDrawerHeader(appState);
            }
            final item = _menuItems[index - 1];
            final selected = _currentIndex == index - 1;
            return ListTile(
              leading: Icon(selected ? item.activeIcon : item.icon),
              title: Text(item.label),
              selected: selected,
              selectedTileColor: AppColors.primary.withValues(alpha: 0.1),
              selectedColor: AppColors.primary,
              onTap: () {
                setState(() => _currentIndex = index - 1);
                Navigator.pop(context);
              },
            );
          },
        ),
      ),
      body: IndexedStack(
        index: _currentIndex,
        children: _pages,
      ),
    );
  }

  Widget _buildDrawerHeader(AppState appState) {
    return DrawerHeader(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          colors: [AppColors.primary, AppColors.sidebar],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          const CircleAvatar(
            radius: 28,
            backgroundColor: Colors.white,
            child: Icon(Icons.storefront, size: 32, color: AppColors.primary),
          ),
          const SizedBox(height: 8),
          Text(
            appState.displayName,
            style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          Text(
            appState.storeName,
            style: const TextStyle(color: Colors.white70, fontSize: 13),
          ),
        ],
      ),
    );
  }
}

class _MenuItem {
  final String label;
  final IconData icon;
  final IconData activeIcon;
  const _MenuItem(this.label, this.icon, this.activeIcon);
}
