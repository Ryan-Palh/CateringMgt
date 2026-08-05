# -*- coding: utf-8 -*-
"""
位置获取模块 —— 用于考勤打卡时记录精确位置
PC端：通过IP获取大致位置 + 高德逆地理编码获取详细地址
Android端：通过 geolocator 插件获取GPS位置
"""
import json
import urllib.request
import urllib.parse
from utils.logger import logger


def get_current_location():
    """
    获取当前位置信息
    返回: {'lat': str, 'lon': str, 'address': str}
    失败时返回 {'lat': '', 'lon': '', 'address': ''}
    """
    result = {'lat': '', 'lon': '', 'address': ''}
    
    try:
        # 方案1：使用高德IP定位API获取坐标
        # 高德Key需要用户自行申请，这里使用免费的无Key方案作为后备
        lat, lon = _get_location_by_ip()
        
        if lat and lon:
            result['lat'] = str(lat)
            result['lon'] = str(lon)
            
            # 方案2：用坐标逆地理编码获取详细地址
            address = _reverse_geocode(lat, lon)
            if address:
                result['address'] = address
            else:
                result['address'] = f'经纬度: {lat},{lon}'
            
            logger.info(f"打卡位置: {result['address']} ({lat}, {lon})")
            return result
    except Exception as e:
        logger.error(f"获取位置失败: {e}")
    
    # 方案3：尝试使用浏览器定位（通过Qt WebEngine）
    try:
        loc = _get_location_by_web()
        if loc and loc.get('lat'):
            return loc
    except Exception as e:
        logger.error(f"Web定位失败: {e}")
    
    logger.warning("无法获取位置信息，打卡将不记录位置")
    return result


def _get_location_by_ip():
    """通过IP获取大致坐标，返回 (lat, lon)"""
    try:
        # 使用 ip-api.com 免费API（无需Key，限每分钟45次）
        url = "http://ip-api.com/json/?lang=zh-CN&fields=status,lat,lon"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('status') == 'success':
                return data.get('lat'), data.get('lon')
    except Exception as e:
        logger.debug(f"ip-api定位失败: {e}")
    
    try:
        # 备用：使用 ipinfo.io
        url = "https://ipinfo.io/json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            loc = data.get('loc', '').split(',')
            if len(loc) == 2:
                return float(loc[0]), float(loc[1])
    except Exception as e:
        logger.debug(f"ipinfo定位失败: {e}")
    
    return None, None


def _reverse_geocode(lat, lon):
    """逆地理编码：坐标转地址，使用OpenStreetMap Nominatim免费API"""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json&accept-language=zh-CN&zoom=18"
        req = urllib.request.Request(url, headers={
            'User-Agent': 'CateringMgt/1.0 (attendance check-in)'
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            address = data.get('display_name', '')
            if address:
                return address
    except Exception as e:
        logger.debug(f"Nominatim逆地理编码失败: {e}")
    
    return ''


def _get_location_by_web():
    """通过Qt WebEngine获取浏览器定位（精度更高）"""
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        from PyQt5.QtCore import QTimer, QEventLoop
        
        view = QWebEngineView()
        loop = QEventLoop()
        result = {}
        
        html = """
        <!DOCTYPE html>
        <html>
        <body>
        <script>
        navigator.geolocation.getCurrentPosition(
            function(pos) {
                window.__lat = pos.coords.latitude;
                window.__lon = pos.coords.longitude;
                window.__acc = pos.coords.accuracy;
                document.title = 'DONE:' + pos.coords.latitude + ',' + pos.coords.longitude + ',' + pos.coords.accuracy;
            },
            function(err) {
                document.title = 'ERROR:' + err.message;
            },
            {enableHighAccuracy: true, timeout: 8000, maximumAge: 0}
        );
        </script>
        </body>
        </html>
        """
        
        view.setHtml(html)
        
        def on_title_changed(title):
            if title.startswith('DONE:'):
                parts = title[5:].split(',')
                result['lat'] = parts[0]
                result['lon'] = parts[1]
                result['accuracy'] = parts[2] if len(parts) > 2 else ''
                # 逆地理编码
                addr = _reverse_geocode(result['lat'], result['lon'])
                result['address'] = addr or f"GPS: {result['lat']},{result['lon']} (精度{result.get('accuracy', '?')}m)"
                loop.quit()
            elif title.startswith('ERROR:'):
                loop.quit()
        
        view.titleChanged.connect(on_title_changed)
        
        # 8秒超时
        QTimer.singleShot(8000, loop.quit)
        loop.exec_()
        
        view.deleteLater()
        return result if result.get('lat') else None
    except Exception as e:
        logger.debug(f"WebEngine定位失败: {e}")
        return None
