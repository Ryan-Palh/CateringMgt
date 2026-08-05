// screens/settings_screen.dart — 设置（个人信息+关于+登出）
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../utils/theme.dart';
import '../utils/app_state.dart';
import 'login_screen.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  @override
  Widget build(BuildContext context) {
    final appState = context.watch<AppState>();
    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: [
        // 个人信息
        Card(
          child: ListTile(
            leading: CircleAvatar(
              backgroundColor: AppColors.primary.withValues(alpha: 0.1),
              child: Icon(Icons.person, color: AppColors.primary),
            ),
            title: Text(appState.displayName, style: const TextStyle(fontWeight: FontWeight.bold)),
            subtitle: Text('门店: ${appState.storeName}'),
          ),
        ),
        const SizedBox(height: AppSpacing.md),

        // 关于
        _buildSectionTitle('关于'),
        Card(
          child: Column(
            children: [
              ListTile(leading: const Icon(Icons.info_outline), title: const Text('版本'), trailing: const Text('v5.0.0')),
              ListTile(leading: const Icon(Icons.storefront), title: const Text('应用名称'), trailing: const Text('餐饮综合管理系统')),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.md),

        // 登出
        Card(
          child: ListTile(
            leading: const Icon(Icons.logout, color: AppColors.danger),
            title: const Text('退出登录', style: TextStyle(color: AppColors.danger)),
            onTap: () async {
              final confirm = await showDialog<bool>(
                context: context,
                builder: (ctx) => AlertDialog(
                  title: const Text('确认退出'),
                  content: const Text('确定要退出登录吗？'),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
                    TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('退出', style: TextStyle(color: AppColors.danger))),
                  ],
                ),
              );
              if (confirm == true && context.mounted) {
                await appState.logout();
                if (context.mounted) {
                  Navigator.pushAndRemoveUntil(
                    context,
                    MaterialPageRoute(builder: (_) => const LoginScreen()),
                    (route) => false,
                  );
                }
              }
            },
          ),
        ),
      ],
    );
  }

  Widget _buildSectionTitle(String title) {
    return Padding(
      padding: const EdgeInsets.only(left: AppSpacing.sm, bottom: AppSpacing.sm),
      child: Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: AppColors.textSecondary)),
    );
  }
}