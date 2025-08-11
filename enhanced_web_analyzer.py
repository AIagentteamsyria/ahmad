# -*- coding: utf-8 -*-

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
from playwright.sync_api import sync_playwright, Error as PlaywrightError
from bs4 import BeautifulSoup, element as bs4_element
import json
import time
import re
import os
import uuid
from urllib.parse import urljoin, urlparse
from collections import defaultdict
from datetime import datetime

app = Flask(__name__)
CORS(app)  # لتمكين CORS للواجهات الأمامية

class WebPageAnalyzer:
    def __init__(self):
        # تعريف العناصر التفاعلية والوسائط والنصوص
        self.MEDIA_TAGS = {'img', 'video', 'audio', 'source', 'picture', 'iframe', 'embed', 'object'}
        self.INTERACTIVE_TAGS = {'a', 'button', 'input', 'select', 'textarea', 'form', 'details', 'summary'}
        self.TEXT_TAGS = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'blockquote', 'span', 'div', 'article', 'section'}
        self.NAVIGATION_TAGS = {'nav', 'menu', 'menuitem'}
        self.LIST_TAGS = {'ul', 'ol', 'dl'}
        
        # أنواع الحقول التفاعلية
        self.INPUT_TYPES = {
            'text': 'نص',
            'email': 'بريد إلكتروني', 
            'password': 'كلمة مرور',
            'number': 'رقم',
            'tel': 'هاتف',
            'url': 'رابط',
            'search': 'بحث',
            'date': 'تاريخ',
            'time': 'وقت',
            'checkbox': 'مربع اختيار',
            'radio': 'اختيار واحد',
            'file': 'ملف',
            'submit': 'إرسال',
            'reset': 'إعادة تعيين',
            'button': 'زر'
        }

    def generate_advanced_selector(self, element: bs4_element.Tag) -> dict:
        """ينشئ مُحددات متقدمة للعنصر مع معلومات إضافية للذكاء الاصطناعي"""
        selectors = {}
        
        # المُحدد بالـ ID (الأقوى)
        if element.has_attr('id'):
            selectors['id_selector'] = f"#{element['id']}"
            selectors['priority'] = 'high'
        
        # المُحدد بالكلاس
        if element.has_attr('class'):
            classes = [c for c in element['class'] if c]
            if classes:
                selectors['class_selector'] = f"{element.name}.{'.'.join(classes)}"
                selectors['classes'] = classes
        
        # المُحدد بالخصائص
        if element.has_attr('name'):
            selectors['name_selector'] = f"{element.name}[name='{element['name']}']"
        
        if element.has_attr('type'):
            selectors['type_selector'] = f"{element.name}[type='{element['type']}']"
        
        # المُحدد النسبي (موقع العنصر)
        selectors['tag_selector'] = element.name
        
        # المسار الهرمي
        path_parts = []
        current = element
        while current and current.name:
            if current.has_attr('id'):
                path_parts.append(f"{current.name}#{current['id']}")
                break
            elif current.has_attr('class'):
                classes = [c for c in current['class'] if c]
                if classes:
                    path_parts.append(f"{current.name}.{classes[0]}")
                else:
                    path_parts.append(current.name)
            else:
                path_parts.append(current.name)
            current = current.parent
            if len(path_parts) > 5:  # تجنب المسارات الطويلة جداً
                break
        
        selectors['hierarchical_path'] = ' > '.join(reversed(path_parts))
        
        return selectors

    def analyze_element_context(self, element: bs4_element.Tag) -> dict:
        """يحلل السياق المحيط بالعنصر لفهم أفضل"""
        context = {}
        
        # العنصر الأب المباشر
        if element.parent and element.parent.name:
            context['parent_tag'] = element.parent.name
            if element.parent.has_attr('class'):
                context['parent_classes'] = element.parent['class']
        
        # العناصر الشقيقة
        siblings = element.find_next_siblings()[:3]  # أول 3 عناصر شقيقة
        context['next_siblings'] = [sib.name for sib in siblings if sib.name]
        
        # النص المحيط
        prev_text = ""
        next_text = ""
        if element.previous_sibling:
            prev_text = str(element.previous_sibling).strip()[:100]
        if element.next_sibling:
            next_text = str(element.next_sibling).strip()[:100]
            
        context['surrounding_text'] = {
            'before': prev_text,
            'after': next_text
        }
        
        # تحديد نوع المنطقة (header, main, footer, nav, etc.)
        region_parent = element.find_parent(['header', 'main', 'footer', 'nav', 'aside', 'section', 'article'])
        if region_parent:
            context['page_region'] = region_parent.name
        
        return context

    def extract_semantic_info(self, element: bs4_element.Tag) -> dict:
        """يستخرج المعلومات الدلالية من العنصر"""
        semantic = {}
        
        # تحليل النص لاستخراج المعنى
        text = element.get_text(strip=True)
        if text:
            semantic['text_content'] = text
            semantic['text_length'] = len(text)
            
            # تصنيف نوع النص
            if re.search(r'\b(تسجيل دخول|login|sign in)\b', text.lower()):
                semantic['text_type'] = 'login'
            elif re.search(r'\b(بحث|search)\b', text.lower()):
                semantic['text_type'] = 'search'
            elif re.search(r'\b(إرسال|submit|send)\b', text.lower()):
                semantic['text_type'] = 'submit'
            elif re.search(r'\b(إلغاء|cancel|close)\b', text.lower()):
                semantic['text_type'] = 'cancel'
            elif re.search(r'^\d+$', text):
                semantic['text_type'] = 'numeric'
            elif re.search(r'@.*\.(com|org|net)', text):
                semantic['text_type'] = 'email'
            elif text.startswith('http'):
                semantic['text_type'] = 'url'
        
        # تحليل الخصائص الدلالية
        if element.has_attr('placeholder'):
            semantic['placeholder'] = element['placeholder']
        
        if element.has_attr('title'):
            semantic['title'] = element['title']
        
        if element.has_attr('alt'):
            semantic['alt_text'] = element['alt']
            
        if element.has_attr('aria-label'):
            semantic['aria_label'] = element['aria-label']
        
        if element.has_attr('role'):
            semantic['role'] = element['role']
        
        return semantic

    def categorize_element_advanced(self, element: bs4_element.Tag) -> dict:
        """يصنف العنصر بطريقة متقدمة مع معلومات تفصيلية"""
        tag_name = element.name.lower()
        category = {}
        
        # التصنيف الرئيسي
        if tag_name in self.MEDIA_TAGS:
            category['primary_type'] = 'media'
            category['media_subtype'] = tag_name
            if element.has_attr('src'):
                category['source_url'] = element['src']
        
        elif tag_name in self.INTERACTIVE_TAGS or element.has_attr('onclick'):
            category['primary_type'] = 'interactive'
            category['interactive_subtype'] = tag_name
            
            # تفاصيل إضافية للعناصر التفاعلية
            if tag_name == 'input':
                input_type = element.get('type', 'text')
                category['input_type'] = input_type
                category['input_type_ar'] = self.INPUT_TYPES.get(input_type, input_type)
            
            elif tag_name == 'a':
                if element.has_attr('href'):
                    category['link_url'] = element['href']
                    # تحديد نوع الرابط
                    href = element['href']
                    if href.startswith('#'):
                        category['link_type'] = 'internal_anchor'
                    elif href.startswith('mailto:'):
                        category['link_type'] = 'email'
                    elif href.startswith('tel:'):
                        category['link_type'] = 'phone'
                    elif 'javascript:' in href:
                        category['link_type'] = 'javascript'
                    else:
                        category['link_type'] = 'external' if 'http' in href else 'internal'
        
        elif tag_name in self.TEXT_TAGS:
            category['primary_type'] = 'text'
            category['text_subtype'] = tag_name
            
            # تصنيف النص حسب الأهمية
            if tag_name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                category['heading_level'] = int(tag_name[1])
                category['importance'] = 'high'
            elif tag_name == 'p':
                category['importance'] = 'medium'
            else:
                category['importance'] = 'low'
        
        elif tag_name in self.NAVIGATION_TAGS:
            category['primary_type'] = 'navigation'
            category['nav_subtype'] = tag_name
        
        elif tag_name in self.LIST_TAGS:
            category['primary_type'] = 'list'
            category['list_subtype'] = tag_name
            # حساب عدد عناصر القائمة
            list_items = element.find_all('li')
            category['list_items_count'] = len(list_items)
        
        else:
            category['primary_type'] = 'container'
            category['container_subtype'] = tag_name
        
        return category

    def extract_page_structure(self, soup: BeautifulSoup) -> dict:
        """يستخرج البنية العامة للصفحة"""
        structure = {
            'page_title': soup.title.string if soup.title else None,
            'meta_description': None,
            'sections': defaultdict(int),
            'forms_count': len(soup.find_all('form')),
            'tables_count': len(soup.find_all('table')),
            'images_count': len(soup.find_all('img')),
            'links_count': len(soup.find_all('a')),
            'headings_hierarchy': defaultdict(int)
        }
        
        # استخراج وصف الصفحة
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            structure['meta_description'] = meta_desc.get('content')
        
        # تحليل بنية العناوين
        for i in range(1, 7):
            headings = soup.find_all(f'h{i}')
            structure['headings_hierarchy'][f'h{i}'] = len(headings)
        
        # تحليل الأقسام الرئيسية
        main_sections = ['header', 'nav', 'main', 'aside', 'footer', 'section', 'article']
        for section in main_sections:
            structure['sections'][section] = len(soup.find_all(section))
        
        return structure

    def analyze_page_content(self, url: str) -> dict:
        """الدالة الرئيسية لتحليل الصفحة"""
        
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp("http://localhost:9222")
                context = browser.contexts[0]
                
                page = context.new_page()
                page.goto(url, wait_until='networkidle', timeout=90000)
                
                time.sleep(2)

                # استخلاص المحتوى
                page_content = page.content()
                soup = BeautifulSoup(page_content, 'lxml')
                all_tags = soup.find_all(True)
                
                # تحليل البنية العامة
                page_structure = self.extract_page_structure(soup)
                
                # قوائم البيانات المحسنة
                csv_data = []
                detailed_elements = []
                summary_stats = {
                    'total_elements': len(all_tags),
                    'by_category': defaultdict(int),
                    'interactive_elements': 0,
                    'media_elements': 0,
                    'text_elements': 0,
                    'high_priority_elements': 0
                }
                
                # تحليل كل عنصر
                for i, element in enumerate(all_tags, 1):
                    # البيانات الأساسية
                    selectors = self.generate_advanced_selector(element)
                    context = self.analyze_element_context(element)
                    semantic = self.extract_semantic_info(element)
                    category = self.categorize_element_advanced(element)
                    
                    # تحديث الإحصائيات
                    primary_type = category.get('primary_type', 'unknown')
                    summary_stats['by_category'][primary_type] += 1
                    
                    if primary_type == 'interactive':
                        summary_stats['interactive_elements'] += 1
                    elif primary_type == 'media':
                        summary_stats['media_elements'] += 1
                    elif primary_type == 'text':
                        summary_stats['text_elements'] += 1
                    
                    if selectors.get('priority') == 'high':
                        summary_stats['high_priority_elements'] += 1
                    
                    # بيانات CSV المحسنة
                    csv_row = {
                        'element_id': i,
                        'tag_name': element.name,
                        'primary_selector': selectors.get('id_selector') or selectors.get('class_selector') or selectors.get('tag_selector'),
                        'all_selectors': json.dumps(selectors, ensure_ascii=False),
                        'category': primary_type,
                        'subcategory': category.get(f'{primary_type}_subtype', ''),
                        'text_content': semantic.get('text_content', ''),
                        'semantic_type': semantic.get('text_type', ''),
                        'importance': category.get('importance', 'normal'),
                        'page_region': context.get('page_region', ''),
                        'is_interactive': primary_type == 'interactive',
                        'has_text': bool(semantic.get('text_content')),
                        'element_attributes': json.dumps(element.attrs, ensure_ascii=False)
                    }
                    csv_data.append(csv_row)
                    
                    # بيانات JSON المفصلة (فقط للعناصر المهمة)
                    if (primary_type in ['interactive', 'media'] or 
                        category.get('importance') == 'high' or
                        semantic.get('text_content', '') and len(semantic['text_content']) > 10):
                        
                        detailed_element = {
                            'element_id': i,
                            'selectors': selectors,
                            'category': category,
                            'semantic_info': semantic,
                            'element_context': context,
                            'raw_attributes': element.attrs
                        }
                        detailed_elements.append(detailed_element)

                # إنشاء النتيجة النهائية
                result = {
                    "analysis_metadata": {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "analyzer_version": "2.0",
                        "purpose": "Enhanced data for AI model analysis",
                        "analyzed_url": url,
                        "page_title": page.title()
                    },
                    "page_structure": dict(page_structure),
                    "elements_summary": dict(summary_stats),
                    "detailed_elements": detailed_elements,
                    "csv_data": csv_data,
                    "ai_assistant_guide": {
                        "element_identification": "استخدم 'id_selector' أولاً، ثم 'class_selector' للتحديد الدقيق",
                        "interaction_priority": "العناصر ذات 'priority': 'high' لها أولوية في التفاعل",
                        "context_usage": "استخدم 'element_context' و 'semantic_info' لفهم الغرض من العنصر",
                        "text_content_guidance": "النصوص مع 'importance': 'high' هي العناوين الرئيسية"
                    }
                }
                
                return {"success": True, "data": result}

            except PlaywrightError as e:
                return {"success": False, "error": f"Playwright Error: {str(e)}"}
            except Exception as e:
                return {"success": False, "error": f"Unexpected Error: {str(e)}"}
            finally:
                if 'browser' in locals() and browser.is_connected():
                    browser.close()

# إنشاء مثيل من المحلل
analyzer = WebPageAnalyzer()

# مجلد لحفظ الملفات المؤقتة
UPLOAD_FOLDER = 'temp_files'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# === API Endpoints ===

@app.route('/', methods=['GET'])
def home():
    """الصفحة الرئيسية للـ API"""
    return jsonify({
        "message": "🔬 محلل الصفحات المحسن للذكاء الاصطناعي - API",
        "version": "2.0",
        "endpoints": {
            "/": "معلومات عن الـ API",
            "/analyze": "تحليل صفحة ويب (POST)",
            "/health": "فحص حالة الخدمة",
            "/download/<file_type>/<session_id>": "تحميل ملفات التحليل"
        },
        "usage": {
            "method": "POST",
            "endpoint": "/analyze",
            "body": {"url": "https://example.com"},
            "requirements": "Chrome browser with --remote-debugging-port=9222"
        }
    })

@app.route('/health', methods=['GET'])
def health_check():
    """فحص حالة الخدمة"""
    try:
        # اختبار الاتصال بـ Chrome
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            browser.close()
            chrome_status = "متصل"
    except:
        chrome_status = "غير متصل"
    
    return jsonify({
        "status": "running",
        "chrome_connection": chrome_status,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route('/analyze', methods=['POST'])
def analyze_webpage():
    """تحليل صفحة ويب"""
    
    # التحقق من البيانات المرسلة
    if not request.is_json:
        return jsonify({"success": False, "error": "يجب إرسال البيانات بصيغة JSON"}), 400
    
    data = request.get_json()
    
    if 'url' not in data:
        return jsonify({"success": False, "error": "يجب تقديم رابط الصفحة (url)"}), 400
    
    url = data['url'].strip()
    
    if not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"success": False, "error": "رابط غير صحيح. يجب أن يبدأ بـ http:// أو https://"}), 400
    
    # خيارات إضافية
    export_files = data.get('export_files', True)  # هل تريد تصدير ملفات CSV و JSON
    
    try:
        # تحليل الصفحة
        result = analyzer.analyze_page_content(url)
        
        if not result['success']:
            return jsonify(result), 500
        
        analysis_data = result['data']
        session_id = str(uuid.uuid4())[:8]  # معرف فريد للجلسة
        
        # حفظ الملفات إذا كان مطلوباً
        if export_files:
            # حفظ CSV
            csv_filename = os.path.join(UPLOAD_FOLDER, f"analysis_{session_id}.csv")
            df = pd.DataFrame(analysis_data['csv_data'])
            df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
            
            # حفظ JSON
            json_filename = os.path.join(UPLOAD_FOLDER, f"analysis_{session_id}.json")
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(analysis_data, f, ensure_ascii=False, indent=2)
            
            analysis_data['download_links'] = {
                'csv': f"/download/csv/{session_id}",
                'json': f"/download/json/{session_id}"
            }
            analysis_data['session_id'] = session_id
        
        # إزالة csv_data من النتيجة لتقليل حجم الاستجابة
        if 'csv_data' in analysis_data:
            del analysis_data['csv_data']
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "message": f"تم تحليل الصفحة بنجاح. تم تحليل {analysis_data['elements_summary']['total_elements']} عنصر",
            "data": analysis_data
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": f"خطأ في التحليل: {str(e)}"}), 500

@app.route('/download/<file_type>/<session_id>', methods=['GET'])
def download_file(file_type, session_id):
    """تحميل ملفات التحليل"""
    
    if file_type not in ['csv', 'json']:
        return jsonify({"error": "نوع ملف غير مدعوم. استخدم csv أو json"}), 400
    
    filename = f"analysis_{session_id}.{file_type}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    
    if not os.path.exists(filepath):
        return jsonify({"error": "الملف غير موجود أو انتهت صلاحيته"}), 404
    
    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/analyze/quick', methods=['POST'])
def quick_analyze():
    """تحليل سريع - يُرجع فقط الملخص والعناصر المهمة"""
    
    if not request.is_json:
        return jsonify({"success": False, "error": "يجب إرسال البيانات بصيغة JSON"}), 400
    
    data = request.get_json()
    
    if 'url' not in data:
        return jsonify({"success": False, "error": "يجب تقديم رابط الصفحة (url)"}), 400
    
    url = data['url'].strip()
    
    try:
        result = analyzer.analyze_page_content(url)
        
        if not result['success']:
            return jsonify(result), 500
        
        analysis_data = result['data']
        
        # تحضير استجابة مبسطة
        quick_response = {
            "analysis_metadata": analysis_data['analysis_metadata'],
            "page_structure": {
                "page_title": analysis_data['page_structure']['page_title'],
                "forms_count": analysis_data['page_structure']['forms_count'],
                "images_count": analysis_data['page_structure']['images_count'],
                "links_count": analysis_data['page_structure']['links_count']
            },
            "elements_summary": analysis_data['elements_summary'],
            "interactive_elements": [
                elem for elem in analysis_data['detailed_elements']
                if elem['category']['primary_type'] == 'interactive'
            ][:10],  # أول 10 عناصر تفاعلية
            "important_headings": [
                elem for elem in analysis_data['detailed_elements']
                if elem['category'].get('importance') == 'high'
            ][:5]  # أول 5 عناوين مهمة
        }
        
        return jsonify({
            "success": True,
            "message": "تم التحليل السريع بنجاح",
            "data": quick_response
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": f"خطأ في التحليل: {str(e)}"}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "الصفحة غير موجودة"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "خطأ داخلي في الخادم"}), 500

if __name__ == '__main__':
    print("=" * 70)
    print("🔬 محلل الصفحات المحسن للذكاء الاصطناعي - Flask API")
    print("=" * 70)
    print("🚀 بدء تشغيل الخادم...")
    print("📡 API endpoints:")
    print("   GET  /                     - معلومات عن API")
    print("   GET  /health               - فحص حالة الخدمة")
    print("   POST /analyze              - تحليل صفحة ويب كامل")
    print("   POST /analyze/quick        - تحليل سريع")
    print("   GET  /download/<type>/<id> - تحميل الملفات")
    print()
    print("--- ⚠️ تذكير مهم ---")
    print("تأكد من تشغيل Google Chrome مع:")
    print("chrome --remote-debugging-port=9222 --user-data-dir=/tmp/chrome-debug")
    print("=" * 70)
    
    app.run(host='0.0.0.0', port=5000, debug=True)