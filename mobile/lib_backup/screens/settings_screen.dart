// screens/settings_screen.dart — 坚果云同步设置
import 'package:flutter/material.dart';
import '../utils/theme.dart';
import '../api/nutstore_sync.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _serverCtrl = TextEditingController();
  final _usernameCtrl = TextEditingController();
  final _passwordCtrl = TextEditingController();
  bool _obscurePwd = true;
  bool _testing = false;
  bool _testResult = false;
  String? _testMsg;

  @override
  void initState() {
    super.initState();
    _loadCredentials();
  }

  Future<void> _loadCredentials() async {
    final creds = await NutstoreSync.getCredentials();
    setState(() {
      _serverCtrl.text = creds['server'] ?? '';
      _usernameCtrl.text = creds['username'] ?? '';
      _passwordCtrl.text = creds['password'] ?? '';
    });
  }

  Future<void> _save() async {
    final server = _serverCtrl.text.trim();
    final username = _usernameCtrl.text.trim();
    final password = _passwordCtrl.text.trim();

    if (server.isEmpty || username.isEmpty || password.isEmpty) {
      _showError('请填写完整');
      return;
    }

    await NutstoreSync.saveCredentials(
      server: server,
      username: username,
      password: password,
    );

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('设置已保存'), backgroundColor: AppColors.success),
      );
      Navigator.pop(context);
    }
  }

  Future<void> _testConn() async {
    setState(() {
      _testing = true;
      _testResult = false;
      _testMsg = null;
    });

    // 先保存再测试
    await NutstoreSync.saveCredentials(
      server: _serverCtrl.text.trim(),
      username: _usernameCtrl.text.trim(),
      password: _passwordCtrl.text.trim(),
    );

    final ok = await NutstoreSync().testConnection();

    setState(() {
      _testing = false;
      _testResult = ok;
      _testMsg = ok ? '连接成功' : '连接失败';
    });

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(_testMsg!),
          backgroundColor: ok ? AppColors.success : AppColors.danger,
        ),
      );
    }
  }

  void _showError(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: AppColors.danger),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('同步设置')),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.md),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.cloud, color: AppColors.primary),
                      const SizedBox(width: AppSpacing.sm),
                      Text('坚果云 WebDAV', style: Theme.of(context).textTheme.titleMedium),
                    ],
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    '配置坚果云 WebDAV 凭据，桌面端和移动端通过同一数据库文件同步数据。',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          TextField(
            controller: _serverCtrl,
            decoration: const InputDecoration(
              labelText: 'WebDAV 服务器地址',
              hintText: 'https://dav.jianguoyun.com/dav/',
              prefixIcon: Icon(Icons.dns_outlined),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          TextField(
            controller: _usernameCtrl,
            decoration: const InputDecoration(
              labelText: '用户名',
              hintText: '坚果云账号',
              prefixIcon: Icon(Icons.person_outline),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          TextField(
            controller: _passwordCtrl,
            obscureText: _obscurePwd,
            decoration: InputDecoration(
              labelText: '应用密码',
              hintText: '坚果云应用密码（非登录密码）',
              prefixIcon: const Icon(Icons.lock_outline),
              suffixIcon: IconButton(
                icon: Icon(_obscurePwd ? Icons.visibility_off : Icons.visibility),
                onPressed: () => setState(() => _obscurePwd = !_obscurePwd),
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _testing ? null : _testConn,
                  icon: _testing
                      ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.wifi_find),
                  label: const Text('测试连接'),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: ElevatedButton.icon(
                  onPressed: _save,
                  icon: const Icon(Icons.save),
                  label: const Text('保存'),
                ),
              ),
            ],
          ),
          if (_testMsg != null) ...[
            const SizedBox(height: AppSpacing.md),
            if (_testResult)
              _buildStatusBanner('连接成功', AppColors.success, Icons.check_circle)
            else
              _buildStatusBanner('连接失败，请检查凭据', AppColors.danger, Icons.error),
          ],
        ],
      ),
    );
  }

  Widget _buildStatusBanner(String msg, Color color, IconData icon) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(AppRadius.sm),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Icon(icon, color: color),
          const SizedBox(width: AppSpacing.sm),
          Text(msg, style: TextStyle(color: color, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }

  @override
  void dispose() {
    _serverCtrl.dispose();
    _usernameCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }
}
