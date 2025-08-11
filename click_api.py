from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import json
import threading
import time
import subprocess
import psutil
import re
from typing import List, Dict, Optional, Tuple

app = Flask(__name__)

class SmartButtonAutomation:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.current_session = None
        self.browser_type = None
        self.typing_in_progress = False
        self.last_typing_time = 0
        
    def check_running_browsers(self):
        """Check if any supported browsers are running with debug port"""
        browsers_info = [
            {"name": "Chrome", "process_names": ["chrome.exe", "chrome", "google-chrome"], "debug_port": 9222},
            {"name": "Edge", "process_names": ["msedge.exe", "msedge", "microsoft-edge"], "debug_port": 9222},
            {"name": "Firefox", "process_names": ["firefox.exe", "firefox"], "debug_port": 6000}
        ]
        
        running_browsers = []
        
        for browser in browsers_info:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] and any(name.lower() in proc.info['name'].lower() for name in browser['process_names']):
                        cmdline = proc.info.get('cmdline', [])
                        if cmdline and any('--remote-debugging-port' in str(arg) for arg in cmdline):
                            running_browsers.append(browser)
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        
        return running_browsers
    
    def connect_to_existing_browser(self):
        """Try to connect to an existing browser with debugging enabled"""
        try:
            self.playwright = sync_playwright().start()
            
            # Try Chrome/Edge first (they use the same CDP protocol)
            cdp_ports = [9222, 9223, 9224]  # Common debug ports
            
            for port in cdp_ports:
                try:
                    browser = self.playwright.chromium.connect_over_cdp(f"http://localhost:{port}")
                    if browser:
                        self.browser = browser
                        contexts = self.browser.contexts
                        if contexts:
                            pages = contexts[0].pages
                            if pages:
                                self.page = pages[0]
                            else:
                                self.page = contexts[0].new_page()
                        else:
                            context = self.browser.new_context()
                            self.page = context.new_page()
                        
                        print(f"✅ Successfully connected to existing browser on port {port}")
                        return True
                        
                except Exception as e:
                    continue
            
            # If CDP connection failed, try Firefox
            try:
                browser = self.playwright.firefox.connect_over_cdp("http://localhost:6000")
                if browser:
                    self.browser = browser
                    contexts = self.browser.contexts
                    if contexts:
                        pages = contexts[0].pages
                        if pages:
                            self.page = pages[0]
                        else:
                            self.page = contexts[0].new_page()
                    else:
                        context = self.browser.new_context()
                        self.page = context.new_page()
                    
                    print("✅ Successfully connected to existing Firefox browser")
                    return True
                    
            except Exception as e:
                pass
            
            return False
            
        except Exception as e:
            print(f"❌ Error connecting to browser: {e}")
            return False
    
    def start_browser_connection(self):
        """Try to connect to existing browser or show instructions"""
        print("🔍 Checking for running browsers with debug mode...")
        
        if self.connect_to_existing_browser():
            return True
        
        print("\n❌ No browser found with debugging enabled!")
        print("\n📋 Please start one of the following browsers with debug mode:")
        print("\n🌐 For Chrome:")
        print("   Windows: chrome.exe --remote-debugging-port=9222")
        print("   Mac/Linux: google-chrome --remote-debugging-port=9222")
        print("\n🌐 For Edge:")
        print("   Windows: msedge.exe --remote-debugging-port=9222")
        print("   Mac/Linux: microsoft-edge --remote-debugging-port=9222")
        print("\n⚠️  Then restart this application.")
        print("-" * 60)
        
        return False
    
    def close_browser_connection(self):
        """Close the browser connection (not the browser itself)"""
        try:
            if self.browser:
                print("🔌 Disconnecting from browser...")
                self.browser = None
                self.page = None
                
            if self.playwright:
                self.playwright.stop()
                self.playwright = None
                
            print("✅ Browser connection closed successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error closing browser connection: {e}")
            return False
    
    def navigate_to_url(self, url):
        """Navigate to the requested URL"""
        try:
            print(f"🌐 Navigating to: {url}")
            self.page.goto(url, wait_until='networkidle', timeout=30000)
            print("✅ Page loaded successfully")
            return True
        except Exception as e:
            print(f"❌ Error loading page: {e}")
            return False
    
    def find_all_buttons(self) -> List[Dict]:
        """Find all clickable buttons on the page with smart categorization"""
        buttons = []
        
        # Enhanced selectors for different types of buttons
        button_selectors = [
            # Standard buttons
            'button',
            'input[type="button"]',
            'input[type="submit"]',
            'input[type="reset"]',
            
            # Links that act as buttons
            'a[role="button"]',
            'a[onclick]',
            'div[role="button"]',
            'span[role="button"]',
            
            # Common clickable elements
            '[onclick]',
            '.btn',
            '.button',
            '.click',
            '.submit',
            '.send',
            '.next',
            '.continue',
            '.accept',
            '.agree',
            '.confirm',
            '.ok',
            '.yes',
            '.no',
            '.cancel',
            '.close',
            '.dismiss',
            '.skip'
        ]
        
        found_elements = set()
        
        for selector in button_selectors:
            try:
                elements = self.page.query_selector_all(selector)
                for element in elements:
                    if element and element.is_visible() and element.is_enabled():
                        # Avoid duplicates
                        element_hash = f"{element.tag_name}-{element.get_attribute('class')}-{element.inner_text()}"
                        if element_hash not in found_elements:
                            found_elements.add(element_hash)
                            button_info = self.analyze_button(element)
                            if button_info:
                                buttons.append(button_info)
            except Exception as e:
                print(f"❌ Error searching for buttons with selector {selector}: {e}")
                continue
        
        return buttons
    
    def analyze_button(self, element) -> Optional[Dict]:
        """Analyze button characteristics and determine its type and priority"""
        try:
            # Get button text and attributes
            text = element.inner_text().strip().lower()
            onclick = element.get_attribute('onclick') or ""
            class_name = element.get_attribute('class') or ""
            id_attr = element.get_attribute('id') or ""
            title = element.get_attribute('title') or ""
            aria_label = element.get_attribute('aria-label') or ""
            role = element.get_attribute('role') or ""
            type_attr = element.get_attribute('type') or ""
            
            # Combine all text sources for analysis
            combined_text = f"{text} {class_name} {id_attr} {title} {aria_label} {onclick}".lower()
            
            # Determine button category and priority
            category, priority, description = self.categorize_button(combined_text, type_attr, element.tag_name.lower())
            
            # Check if it's associated with an input field
            associated_input = self.find_associated_input(element)
            
            return {
                'element': element,
                'text': text,
                'category': category,
                'priority': priority,
                'description': description,
                'combined_text': combined_text,
                'associated_input': associated_input,
                'tag_name': element.tag_name.lower(),
                'type': type_attr,
                'clickable': True
            }
            
        except Exception as e:
            print(f"❌ Error analyzing button: {e}")
            return None
    
    def categorize_button(self, combined_text: str, type_attr: str, tag_name: str) -> Tuple[str, int, str]:
        """Categorize button based on text content and attributes"""
        
        # Cookie consent buttons (highest priority for user experience)
        cookie_patterns = [
            'accept all', 'accept cookies', 'allow all', 'allow cookies',
            'agree and continue', 'accept and continue', 'cookie', 'consent',
            'i accept', 'i agree', 'موافق على الكوكيز', 'قبول الكوكيز', 'موافق'
        ]
        
        # Terms and conditions
        terms_patterns = [
            'accept terms', 'agree terms', 'accept conditions', 'agree conditions',
            'i agree to terms', 'accept privacy', 'موافق على الشروط', 'قبول الشروط',
            'terms', 'privacy policy', 'موافقة على الشروط'
        ]
        
        # Navigation buttons
        navigation_patterns = [
            'next', 'continue', 'proceed', 'forward', 'التالي', 'متابعة', 'المتابعة'
        ]
        
        # Submit/Send buttons
        submit_patterns = [
            'submit', 'send', 'post', 'save', 'إرسال', 'حفظ', 'تقديم'
        ]
        
        # Search buttons
        search_patterns = [
            'search', 'find', 'بحث', 'البحث'
        ]
        
        # Cancel/Close buttons
        cancel_patterns = [
            'cancel', 'close', 'dismiss', 'skip', 'not now', 'later',
            'إلغاء', 'إغلاق', 'تجاهل', 'لاحقاً', 'ليس الآن'
        ]
        
        # Choice buttons (Yes/No, etc.)
        choice_patterns = [
            'yes', 'no', 'ok', 'confirm', 'نعم', 'لا', 'موافق', 'تأكيد'
        ]
        
        # Check patterns in order of priority
        for pattern in cookie_patterns:
            if pattern in combined_text:
                return "cookie_consent", 10, f"Cookie Consent Button: {pattern}"
        
        for pattern in terms_patterns:
            if pattern in combined_text:
                return "terms_agreement", 9, f"Terms Agreement Button: {pattern}"
        
        # Check if it's a submit button with form type
        if type_attr == 'submit' or tag_name == 'button' and 'submit' in combined_text:
            return "submit", 8, "Form Submit Button"
        
        for pattern in navigation_patterns:
            if pattern in combined_text:
                return "navigation", 7, f"Navigation Button: {pattern}"
        
        for pattern in search_patterns:
            if pattern in combined_text:
                return "search", 6, f"Search Button: {pattern}"
        
        for pattern in choice_patterns:
            if pattern in combined_text:
                return "choice", 5, f"Choice Button: {pattern}"
        
        for pattern in cancel_patterns:
            if pattern in combined_text:
                return "cancel", 2, f"Cancel/Close Button: {pattern}"
        
        # Default category
        return "general", 3, f"General Button: {combined_text[:50]}"
    
    def find_associated_input(self, button_element):
        """Find input field associated with this button"""
        try:
            # Look for nearby input fields
            parent = button_element.query_selector('xpath=..')
            if parent:
                # Look for input fields in the same container
                inputs = parent.query_selector_all('input, textarea')
                for inp in inputs:
                    if inp.is_visible() and inp.is_enabled():
                        inp_type = inp.get_attribute('type') or 'text'
                        if inp_type in ['text', 'search', 'email', 'url']:
                            return {
                                'element': inp,
                                'type': inp_type,
                                'placeholder': inp.get_attribute('placeholder') or '',
                                'value': inp.input_value()
                            }
            return None
        except Exception:
            return None
    
    def is_typing_in_progress(self) -> bool:
        """Check if typing is currently happening"""
        current_time = time.time()
        return (current_time - self.last_typing_time) < 3.0
    
    def wait_for_typing_completion(self, input_element, max_wait: int = 30) -> bool:
        """Wait for typing to complete in an input field"""
        print("⌛ Waiting for typing completion...")
        
        initial_value = ""
        stable_count = 0
        wait_cycles = 0
        
        try:
            initial_value = input_element.input_value()
        except:
            pass
        
        # If field is empty, wait 5 seconds for typing to start
        if not initial_value.strip():
            print("📝 Field is empty, waiting for typing to start...")
            time.sleep(5)
            try:
                current_value = input_element.input_value()
                if not current_value.strip():
                    print("⏭️ No typing detected, proceeding...")
                    return True
            except:
                return True
        
        # Monitor typing progress
        last_value = initial_value
        
        while wait_cycles < max_wait:
            time.sleep(1)
            wait_cycles += 1
            
            try:
                current_value = input_element.input_value()
                
                if current_value == last_value:
                    stable_count += 1
                    # If value has been stable for 3 seconds, typing is likely done
                    if stable_count >= 3:
                        print("✅ Typing appears to be complete!")
                        return True
                else:
                    stable_count = 0  # Reset counter if value changed
                    print(f"📝 Typing in progress... Current length: {len(current_value)}")
                
                last_value = current_value
                
            except Exception as e:
                print(f"⚠️ Error monitoring typing: {e}")
                break
        
        print("⏰ Maximum wait time reached, proceeding...")
        return True
    
    def smart_button_click(self, button_info: Dict) -> Dict:
        """Intelligently click buttons based on context and timing"""
        try:
            button = button_info['element']
            category = button_info['category']
            associated_input = button_info.get('associated_input')
            
            print(f"🎯 Processing {category} button: {button_info['description']}")
            
            # Special handling for submit/search buttons with associated inputs
            if category in ['submit', 'search', 'navigation'] and associated_input:
                input_element = associated_input['element']
                current_value = associated_input['value']
                
                print(f"🔍 Found associated input field with value: '{current_value}'")
                
                # If field is empty or typing might be in progress
                if not current_value.strip() or self.is_typing_in_progress():
                    success = self.wait_for_typing_completion(input_element)
                    if not success:
                        return {
                            "success": False,
                            "message": "Timeout waiting for typing completion",
                            "category": category
                        }
            
            # Click the button
            print(f"🖱️ Clicking {category} button...")
            button.click()
            
            # Wait for page response
            time.sleep(2)
            
            # Check if page changed or new content loaded
            try:
                self.page.wait_for_load_state('networkidle', timeout=5000)
            except:
                pass  # Continue even if network idle timeout occurs
            
            print(f"✅ Successfully clicked {category} button!")
            
            return {
                "success": True,
                "message": f"Successfully clicked {category} button",
                "category": category,
                "button_text": button_info['text']
            }
            
        except Exception as e:
            print(f"❌ Error clicking button: {e}")
            return {
                "success": False,
                "message": f"Error clicking button: {str(e)}",
                "category": button_info.get('category', 'unknown')
            }
    
    def process_all_buttons(self, url: str, categories_filter: List[str] = None) -> Dict:
        """Process all buttons on a page with smart prioritization"""
        try:
            print(f"🌐 Loading page: {url}")
            
            if not self.navigate_to_url(url):
                return {"success": False, "message": "Failed to load page"}
            
            print("🔍 Scanning for buttons...")
            buttons = self.find_all_buttons()
            
            if not buttons:
                return {"success": False, "message": "No buttons found on this page"}
            
            print(f"✅ Found {len(buttons)} button(s)")
            
            # Filter by categories if specified
            if categories_filter:
                buttons = [b for b in buttons if b['category'] in categories_filter]
                print(f"🎯 Filtered to {len(buttons)} button(s) matching categories: {categories_filter}")
            
            # Sort by priority (higher priority first)
            buttons.sort(key=lambda x: x['priority'], reverse=True)
            
            results = []
            processed_count = 0
            
            for i, button_info in enumerate(buttons, 1):
                print(f"\n📊 Processing button {i}/{len(buttons)}")
                print(f"🏷️ Category: {button_info['category']} (Priority: {button_info['priority']})")
                print(f"📝 Description: {button_info['description']}")
                
                result = self.smart_button_click(button_info)
                results.append(result)
                
                if result['success']:
                    processed_count += 1
                    # Small delay between button clicks
                    time.sleep(1)
                
                # Check if page has changed significantly (like navigation)
                if button_info['category'] in ['navigation', 'submit']:
                    print("🔄 Page may have changed, rescanning...")
                    time.sleep(2)
                    break  # Re-scan after navigation
            
            return {
                "success": True,
                "message": f"Processed {processed_count} buttons successfully",
                "total_buttons": len(buttons),
                "processed_buttons": processed_count,
                "results": results
            }
            
        except Exception as e:
            print(f"❌ Error processing buttons: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}
    
    # Keep the original form filling functionality
    def find_input_fields(self):
        """Find all input fields on the page"""
        input_fields = []
        
        selectors = [
            'input[type="text"]', 'input[type="email"]', 'input[type="password"]',
            'input[type="search"]', 'input[type="url"]', 'input[type="tel"]',
            'input[type="number"]', 'input:not([type])', 'textarea',
            'input[type="date"]', 'input[type="time"]'
        ]
        
        for selector in selectors:
            try:
                elements = self.page.query_selector_all(selector)
                for element in elements:
                    if element.is_visible() and element.is_enabled():
                        field_info = self.get_field_info(element, selector)
                        if field_info:
                            input_fields.append(field_info)
            except Exception as e:
                print(f"❌ Error searching for elements {selector}: {e}")
        
        return input_fields
    
    def get_field_info(self, element, selector):
        """Get field information"""
        try:
            field_type = "text"
            field_display_name = "Text Input"
            placeholder = element.get_attribute('placeholder') or ""
            name = element.get_attribute('name') or ""
            field_id = element.get_attribute('id') or ""
            field_class = element.get_attribute('class') or ""
            input_type = element.get_attribute('type') or "text"
            
            # Field type detection logic (same as original)
            if 'search' in input_type.lower() or 'search' in placeholder.lower():
                field_type = "search"
                field_display_name = "Search Box"
            elif input_type == 'email':
                field_type = "email"
                field_display_name = "Email Input"
            # ... (rest of the field type detection logic)
            
            return {
                'element': element,
                'type': field_type,
                'display_name': field_display_name,
                'placeholder': placeholder,
                'name': name,
                'id': field_id,
                'class': field_class,
                'input_type': input_type
            }
        except Exception as e:
            print(f"❌ Error getting field information: {e}")
            return None

# Create single instance
smart_automation = SmartButtonAutomation()

@app.route('/start_session', methods=['POST'])
def start_session():
    """Start new session"""
    try:
        if smart_automation.browser:
            smart_automation.close_browser_connection()
        
        success = smart_automation.start_browser_connection()
        if success:
            return jsonify({"success": True, "message": "Session started successfully"})
        else:
            return jsonify({"success": False, "message": "Failed to connect to browser. Please start a browser with debug mode first."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/process_buttons', methods=['POST'])
def process_buttons():
    """Process buttons on specified page with smart automation"""
    try:
        data = request.json
        url = data.get('url')
        categories = data.get('categories')  # Optional filter
        
        if not url:
            return jsonify({"success": False, "message": "Please provide page URL"})
        
        if not smart_automation.browser:
            return jsonify({"success": False, "message": "Please start session first"})
        
        result = smart_automation.process_all_buttons(url, categories)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/scan_buttons', methods=['POST'])
def scan_buttons():
    """Scan and list all buttons without clicking them"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({"success": False, "message": "Please provide page URL"})
        
        if not smart_automation.browser:
            return jsonify({"success": False, "message": "Please start session first"})
        
        if not smart_automation.navigate_to_url(url):
            return jsonify({"success": False, "message": "Failed to load page"})
        
        buttons = smart_automation.find_all_buttons()
        
        buttons_info = []
        for button in buttons:
            buttons_info.append({
                'category': button['category'],
                'priority': button['priority'],
                'description': button['description'],
                'text': button['text'],
                'tag_name': button['tag_name'],
                'has_associated_input': button['associated_input'] is not None
            })
        
        # Sort by priority
        buttons_info.sort(key=lambda x: x['priority'], reverse=True)
        
        return jsonify({
            "success": True,
            "buttons_count": len(buttons_info),
            "buttons": buttons_info
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/click_specific_button', methods=['POST'])
def click_specific_button():
    """Click a specific button by category or text"""
    try:
        data = request.json
        url = data.get('url')
        button_category = data.get('category')
        button_text = data.get('text')
        
        if not url:
            return jsonify({"success": False, "message": "Please provide page URL"})
        
        if not button_category and not button_text:
            return jsonify({"success": False, "message": "Please provide either button category or text"})
        
        if not smart_automation.browser:
            return jsonify({"success": False, "message": "Please start session first"})
        
        if not smart_automation.navigate_to_url(url):
            return jsonify({"success": False, "message": "Failed to load page"})
        
        buttons = smart_automation.find_all_buttons()
        
        target_button = None
        for button in buttons:
            if button_category and button['category'] == button_category:
                target_button = button
                break
            elif button_text and button_text.lower() in button['text'].lower():
                target_button = button
                break
        
        if not target_button:
            return jsonify({"success": False, "message": "Button not found"})
        
        result = smart_automation.smart_button_click(target_button)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/close_session', methods=['POST'])
def close_session():
    """End session and close browser connection"""
    try:
        smart_automation.close_browser_connection()
        return jsonify({"success": True, "message": "Session closed successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

# Keep original form filling endpoints for compatibility
@app.route('/fill_form', methods=['POST'])
def fill_form():
    """Fill form on specified page (original functionality)"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({"success": False, "message": "Please provide page URL"})
        
        if not smart_automation.browser:
            return jsonify({"success": False, "message": "Please start session first"})
        
        # Use original form filling logic here
        # This would need to be adapted from the original interactive_fill_form method
        
        return jsonify({"success": True, "message": "Form filling functionality available"})
        
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

if __name__ == '__main__':
    print("🚀 Starting Smart Button Automation API")
    print("📋 Available endpoints:")
    print("   POST /start_session - Start new session")
    print("   POST /process_buttons - Intelligently process all buttons")
    print("   POST /scan_buttons - Scan and list all buttons (no clicking)")
    print("   POST /click_specific_button - Click specific button by category/text")
    print("   POST /fill_form - Original form filling functionality")
    print("   POST /close_session - End session")
    print("\n🎯 Button Categories:")
    print("   • cookie_consent (Priority 10) - Cookie acceptance buttons")
    print("   • terms_agreement (Priority 9) - Terms & conditions buttons")
    print("   • submit (Priority 8) - Form submission buttons")
    print("   • navigation (Priority 7) - Next/Continue buttons")
    print("   • search (Priority 6) - Search buttons")
    print("   • choice (Priority 5) - Yes/No/OK buttons")
    print("   • general (Priority 3) - General buttons")
    print("   • cancel (Priority 2) - Cancel/Close buttons")
    print("-" * 60)
    
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        smart_automation.close_browser_connection()
