from flask import Flask, request, jsonify
from playwright.sync_api import sync_playwright
import json
import threading
import time
import subprocess
import psutil

app = Flask(__name__)

class FormFiller:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.current_session = None
        self.browser_type = None
    
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
                    # Try to connect via CDP (Chrome Debug Protocol)
                    browser = self.playwright.chromium.connect_over_cdp(f"http://localhost:{port}")
                    if browser:
                        self.browser = browser
                        # Get existing page or create new one
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
        
        # First try to connect directly
        if self.connect_to_existing_browser():
            return True
        
        # If no connection possible, show instructions
        print("\n❌ No browser found with debugging enabled!")
        print("\n📋 Please start one of the following browsers with debug mode:")
        print("\n🌐 For Chrome:")
        print("   Windows: chrome.exe --remote-debugging-port=9222")
        print("   Mac/Linux: google-chrome --remote-debugging-port=9222")
        print("\n🌐 For Edge:")
        print("   Windows: msedge.exe --remote-debugging-port=9222")
        print("   Mac/Linux: microsoft-edge --remote-debugging-port=9222")
        print("\n🌐 For Firefox (add-on required):")
        print("   Install 'Marionette' add-on and start with --marionette --remote-debugging-port=6000")
        print("\n⚠️  Then restart this application.")
        print("-" * 60)
        
        return False
    
    def close_browser_connection(self):
        """Close the browser connection (not the browser itself)"""
        try:
            if self.browser:
                # Don't close the actual browser, just disconnect
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
    
    def find_input_fields(self):
        """Find all input fields on the page"""
        input_fields = []
        
        # Search for different types of input fields
        selectors = [
            'input[type="text"]',
            'input[type="email"]', 
            'input[type="password"]',
            'input[type="search"]',
            'input[type="url"]',
            'input[type="tel"]',
            'input[type="number"]',
            'input:not([type])',  # input without specified type (defaults to text)
            'textarea',
            'input[type="date"]',
            'input[type="time"]'
        ]
        
        for selector in selectors:
            try:
                elements = self.page.query_selector_all(selector)
                for element in elements:
                    # Check if element is visible and interactive
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
            
            # Determine field type based on attributes
            input_type = element.get_attribute('type') or "text"
            
            # Advanced field type detection with display names
            if 'search' in input_type.lower() or 'search' in placeholder.lower() or 'search' in name.lower() or 'search' in field_class.lower():
                field_type = "search"
                field_display_name = "Search Box"
            elif input_type == 'email' or 'email' in placeholder.lower() or 'mail' in name.lower() or 'email' in field_class.lower():
                field_type = "email"
                field_display_name = "Email Input"
            elif input_type == 'password' or 'password' in placeholder.lower() or 'pass' in name.lower() or 'password' in field_class.lower():
                field_type = "password"
                field_display_name = "Password Input"
            elif input_type == 'url' or 'url' in placeholder.lower() or 'website' in placeholder.lower():
                field_type = "url"
                field_display_name = "URL Input"
            elif selector == 'textarea' or element.tag_name.lower() == 'textarea':
                field_type = "textarea"
                if 'comment' in placeholder.lower() or 'comment' in name.lower():
                    field_display_name = "Comments Box"
                elif 'message' in placeholder.lower() or 'message' in name.lower():
                    field_display_name = "Message Box"
                elif 'description' in placeholder.lower() or 'description' in name.lower():
                    field_display_name = "Description Box"
                else:
                    field_display_name = "Text Area"
            elif input_type == 'tel' or 'phone' in placeholder.lower() or 'tel' in name.lower():
                field_type = "phone"
                field_display_name = "Phone Number Input"
            elif input_type == 'number' or 'number' in placeholder.lower():
                field_type = "number"
                field_display_name = "Number Input"
            elif input_type == 'date':
                field_type = "date"
                field_display_name = "Date Input"
            elif input_type == 'time':
                field_type = "time"
                field_display_name = "Time Input"
            elif 'name' in placeholder.lower() or 'name' in name.lower():
                field_type = "name"
                field_display_name = "Name Input"
            elif 'username' in placeholder.lower() or 'username' in name.lower() or 'user' in name.lower():
                field_type = "username"
                field_display_name = "Username Input"
            elif 'address' in placeholder.lower() or 'address' in name.lower():
                field_type = "address"
                field_display_name = "Address Input"
            elif 'age' in placeholder.lower() or 'age' in name.lower():
                field_type = "age"
                field_display_name = "Age Input"
            elif 'title' in placeholder.lower() or 'title' in name.lower():
                field_type = "title"
                field_display_name = "Title Input"
            else:
                field_type = "text"
                field_display_name = "Text Input"
            
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
    
    def fill_field(self, element, value, field_type):
        """Fill field with the requested value"""
        try:
            # Focus on the field first
            element.click()
            
            # Clear current content
            element.fill("")
            
            # Type new value
            element.type(value, delay=100)  # delay for natural simulation
            
            print(f"✅ Successfully filled {field_type} field with: {value}")
            return True
            
        except Exception as e:
            print(f"❌ Error filling field: {e}")
            return False
    
    def interactive_fill_form(self, url):
        """Fill form interactively"""
        print(f"🌐 Loading page: {url}")
        
        if not self.navigate_to_url(url):
            return {"success": False, "message": "Failed to load page"}
        
        print("🔍 Searching for input fields...")
        input_fields = self.find_input_fields()
        
        if not input_fields:
            print("❌ No input fields found on this page")
            return {"success": False, "message": "No input fields found"}
        
        print(f"✅ Found {len(input_fields)} input field(s)")
        print("-" * 50)
        
        filled_fields = 0
        skipped_fields = 0
        
        for i, field in enumerate(input_fields, 1):
            field_description = self.get_field_description(field)
            
            print(f"\n📝 Field {i}/{len(input_fields)}: {field['display_name']}")
            print(f"🏷️  Field Type: {field_description}")
            
            if field['placeholder']:
                print(f"💡 Placeholder: {field['placeholder']}")
            
            # Create detailed prompt based on field type
            prompt_message = self.get_input_prompt(field)
            user_input = input(prompt_message).strip()
            
            if user_input:
                success = self.fill_field(field['element'], user_input, field['display_name'])
                if success:
                    filled_fields += 1
                    time.sleep(0.5)  # short pause for page processing
                else:
                    print(f"⚠️  Failed to fill {field['display_name']} field")
            else:
                print(f"⏭️  Skipped {field['display_name']} field")
                skipped_fields += 1
        
        print("\n" + "="*50)
        print(f"✅ Form processing completed!")
        print(f"📊 Statistics:")
        print(f"   • Fields filled: {filled_fields}")
        print(f"   • Fields skipped: {skipped_fields}")
        print(f"   • Total fields: {len(input_fields)}")
        
        return {
            "success": True, 
            "message": "Form filling completed",
            "stats": {
                "total_fields": len(input_fields),
                "filled_fields": filled_fields,
                "skipped_fields": skipped_fields
            }
        }
    
    def get_field_description(self, field):
        """Detailed field description"""
        desc = field['display_name']
        
        if field['name']:
            desc += f" (name: {field['name']})"
        elif field['id']:
            desc += f" (id: {field['id']})"
        
        return desc
    
    def get_input_prompt(self, field):
        """Generate appropriate input prompt based on field type"""
        field_type = field['type']
        display_name = field['display_name']
        
        prompts = {
            'search': f"🔍 Enter search term for {display_name} (or press Enter to skip): ",
            'email': f"📧 Enter email address for {display_name} (or press Enter to skip): ",
            'password': f"🔒 Enter password for {display_name} (or press Enter to skip): ",
            'url': f"🌐 Enter URL for {display_name} (or press Enter to skip): ",
            'textarea': f"📄 Enter text for {display_name} (or press Enter to skip): ",
            'phone': f"📱 Enter phone number for {display_name} (or press Enter to skip): ",
            'number': f"🔢 Enter number for {display_name} (or press Enter to skip): ",
            'date': f"📅 Enter date for {display_name} (YYYY-MM-DD format, or press Enter to skip): ",
            'time': f"⏰ Enter time for {display_name} (HH:MM format, or press Enter to skip): ",
            'name': f"👤 Enter name for {display_name} (or press Enter to skip): ",
            'username': f"👨‍💻 Enter username for {display_name} (or press Enter to skip): ",
            'address': f"📍 Enter address for {display_name} (or press Enter to skip): ",
            'age': f"🎂 Enter age for {display_name} (or press Enter to skip): ",
            'title': f"📝 Enter title for {display_name} (or press Enter to skip): "
        }
        
        return prompts.get(field_type, f"🖊️  Enter value for {display_name} (or press Enter to skip): ")

# Create single FormFiller instance
form_filler = FormFiller()

@app.route('/start_session', methods=['POST'])
def start_session():
    """Start new session"""
    try:
        if form_filler.browser:
            form_filler.close_browser_connection()
        
        success = form_filler.start_browser_connection()
        if success:
            return jsonify({"success": True, "message": "Session started successfully"})
        else:
            return jsonify({"success": False, "message": "Failed to connect to browser. Please start a browser with debug mode first."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/fill_form', methods=['POST'])
def fill_form():
    """Fill form on specified page"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({"success": False, "message": "Please provide page URL"})
        
        if not form_filler.browser:
            return jsonify({"success": False, "message": "Please start session first"})
        
        # Run form filler in separate thread to allow interaction
        def run_form_filler():
            result = form_filler.interactive_fill_form(url)
            return result
        
        result = run_form_filler()
        return jsonify(result)
        
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/close_session', methods=['POST'])
def close_session():
    """End session and close browser connection"""
    try:
        form_filler.close_browser_connection()
        return jsonify({"success": True, "message": "Session closed successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/get_fields', methods=['POST'])
def get_fields():
    """Get list of fields on page without filling them"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({"success": False, "message": "Please provide page URL"})
        
        if not form_filler.browser:
            return jsonify({"success": False, "message": "Please start session first"})
        
        if not form_filler.navigate_to_url(url):
            return jsonify({"success": False, "message": "Failed to load page"})
        
        input_fields = form_filler.find_input_fields()
        
        fields_info = []
        for field in input_fields:
            fields_info.append({
                'type': field['type'],
                'display_name': field['display_name'],
                'placeholder': field['placeholder'],
                'name': field['name'],
                'id': field['id']
            })
        
        return jsonify({
            "success": True, 
            "fields_count": len(fields_info),
            "fields": fields_info
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

if __name__ == '__main__':
    print("🚀 Starting Form Filler API")
    print("📋 Available endpoints:")
    print("   POST /start_session - Start new session")
    print("   POST /fill_form - Fill form (requires url in JSON)")
    print("   POST /get_fields - Get field list (requires url in JSON)")
    print("   POST /close_session - End session")
    print("-" * 60)
    
    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    finally:
        # Make sure to close browser connection on app exit
        form_filler.close_browser_connection()