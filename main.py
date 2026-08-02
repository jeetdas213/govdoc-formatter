import urllib.request 
import json
import io
import base64
import os
import flet as ft
from PIL import Image, ImageDraw, ImageFont

APP_VERSION = "1.0.0"
REMOTE_EXAMS_URL = "https://raw.githubusercontent.com/jeetdas213/govdoc-formatter/main/assets/exams.json"
REMOTE_VERSION_URL = "https://raw.githubusercontent.com/jeetdas213/govdoc-formatter/main/version.json"

# Load exam presets from local JSON
def load_presets():
    presets = []
    local_json_path = os.path.join(os.path.dirname(__file__), "assets", "exams.json")
    
    # 1. Load local offline backup
    if os.path.exists(local_json_path):
        try:
            with open(local_json_path, "r", encoding="utf-8") as f:
                presets = json.load(f)
        except Exception:
            pass

    # 2. One-way fetch from GitHub
    if "YOUR_GITHUB_USERNAME" not in REMOTE_EXAMS_URL:
        try:
            req = urllib.request.Request(
                REMOTE_EXAMS_URL,
                headers={'User-Agent': 'GovDocFormatterApp/1.0'}
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                if response.status == 200:
                    remote_data = json.loads(response.read().decode('utf-8'))
                    if remote_data and isinstance(remote_data, list):
                        presets = remote_data
        except Exception:
            pass

    return presets

EXAM_PRESETS = load_presets()

# Unit to Pixels at 300 DPI
def to_pixels(val, unit):
    try:
        val = float(val)
        if unit == 'cm':
            return int(round(val * 300 / 2.54))
        elif unit == 'mm':
            return int(round(val * 300 / 25.4))
        elif unit == 'in':
            return int(round(val * 300))
        return int(round(val))
    except ValueError:
        return 350

class WorkspaceTab(ft.UserControl):
    def __init__(self, is_signature=False):
        super().__init__()
        self.is_signature = is_signature
        self.raw_image_bytes = None
        self.processed_bytes = None
        self.offset_x = 0.0
        self.offset_y = 0.0  
        
    def build(self):
        # UI Input Components
        filtered_presets = [p for p in EXAM_PRESETS if (p['type'] == 'signature' if self.is_signature else p['type'] == 'photo')]
        
        options = [ft.dropdown.Option("Custom / Manual Settings")] + [ft.dropdown.Option(p["examName"]) for p in filtered_presets]
        
        self.preset_dropdown = ft.Dropdown(
            label="Select Exam Preset",
            value="Custom / Manual Settings",
            options=options,
            on_change=self.on_preset_change
        )
        
        self.width_field = ft.TextField(label="Width", value="4.0" if self.is_signature else "350", expand=True, on_change=self.process_image)
        self.height_field = ft.TextField(label="Height", value="2.0" if self.is_signature else "450", expand=True, on_change=self.process_image)
        self.unit_dropdown = ft.Dropdown(
            value="cm" if self.is_signature else "px",
            options=[ft.dropdown.Option("px"), ft.dropdown.Option("cm"), ft.dropdown.Option("mm"), ft.dropdown.Option("in")],
            width=80,
            on_change=self.process_image
        )
        
        self.min_kb_field = ft.TextField(label="Min KB", value="10" if self.is_signature else "20", expand=True, on_change=self.process_image)
        self.max_kb_field = ft.TextField(label="Max KB", value="20" if self.is_signature else "50", expand=True, on_change=self.process_image)
        
        self.format_dropdown = ft.Dropdown(
            value="JPG",
            options=[ft.dropdown.Option("JPG"), ft.dropdown.Option("JPEG"), ft.dropdown.Option("PNG")],
            on_change=self.process_image
        )

        # Photo-specific banner overlay
        self.banner_checkbox = ft.Checkbox(label="Add Candidate Name & Date Banner", value=False, on_change=self.process_image)
        self.name_field = ft.TextField(label="Candidate Name", visible=False, on_change=self.process_image)
        self.date_field = ft.TextField(label="Date of Photo (e.g. 01/08/2026)", visible=False, on_change=self.process_image)
        
        # Signature-specific ink enhancer
        self.ink_checkbox = ft.Checkbox(label="Pure Black/White Ink Enhancer", value=True if self.is_signature else False, on_change=self.process_image)
        self.threshold_slider = ft.Slider(min=50, max=200, value=128, divisions=15, label="Ink Threshold: {value}", on_change=self.process_image)
        self.zoom_slider = ft.Slider(
            min=1.0,
            max=3.0,
            value=1.0,
            divisions=20,
            label="Zoom: {value}x",
            on_change=self.process_image
        )
        # Position Fine-Tuning Sliders
        self.offset_x_slider = ft.Slider(min=-1.0, max=1.0, value=0.0, divisions=40, label="Left/Right: {value}", on_change=self.on_slider_move)
        self.offset_y_slider = ft.Slider(min=-1.0, max=1.0, value=0.0, divisions=40, label="Up/Down: {value}", on_change=self.on_slider_move)


        # Status & Preview
        self.compliance_text = ft.Text(value="Upload an image to start validation", weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_700)
        self.compliance_container = ft.Container(
            content=self.compliance_text,
            padding=10,
            bgcolor=ft.colors.BLUE_50,
            border_radius=8,
            border=ft.border.all(1, ft.colors.BLUE)
        )
        
        self.image_preview = ft.Image(fit=ft.ImageFit.FILL)
        
        self.preview_card = ft.Container(
            content=self.image_preview,
            border=ft.border.all(1.5, ft.colors.BLUE_GREY_400),
            border_radius=4,
            shadow=ft.BoxShadow(
                blur_radius=10,
                spread_radius=1,
                color=ft.colors.BLACK26,
                offset=ft.Offset(0, 4)
            )
        )
        self.gesture_detector = ft.GestureDetector(
            content=self.preview_card,
            on_pan_update=self.on_image_pan,
            mouse_cursor=ft.MouseCursor.MOVE
        )
        self.filename_field = ft.TextField(
            label="Custom Output Filename (Optional)",
            hint_text="e.g. Soumya_SSC_Photo",
            value=""
        )
        
        # File Pickers
        self.file_picker = ft.FilePicker(on_result=self.on_file_selected)
        self.save_picker = ft.FilePicker(on_result=self.on_save_location)
        
        # Assemble Controls Column
        controls = [
            self.file_picker,
            self.save_picker,
            self.preset_dropdown,
            ft.Row([self.width_field, self.height_field, self.unit_dropdown]),
            ft.Row([self.min_kb_field, self.max_kb_field]),
            self.format_dropdown,
            self.filename_field, 
            ft.Text("Zoom / Crop Focus:"),  # <--- Added Label
            self.zoom_slider,               # <--- Added Slider
            ft.Text("Adjust Frame Position (Up / Down):"),
            self.offset_y_slider,
            ft.Text("Adjust Frame Position (Left / Right):"),
            self.offset_x_slider,
        ]
        
        if not self.is_signature:
            controls.extend([
                self.banner_checkbox,
                self.name_field,
                self.date_field
            ])
        else:
            controls.extend([
                self.ink_checkbox,
                ft.Text("Ink Sensitivity:"),
                self.threshold_slider
            ])

        return ft.Row([
            ft.Container(
                content=ft.Column(controls, scroll=ft.ScrollMode.AUTO),
                expand=4,
                bgcolor=ft.colors.GREY_100,
                padding=15,
                border_radius=10
            ),
            ft.Container(
                content=ft.Column([
                    self.compliance_container,
                    ft.Container(content=self.gesture_detector, expand=True, alignment=ft.alignment.center, bgcolor=ft.colors.BLUE_GREY_50, border_radius=10, padding=10),
                    ft.Row([
                        ft.ElevatedButton("Choose File", icon=ft.icons.FOLDER_OPEN, on_click=lambda _: self.file_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE)),
                        ft.ElevatedButton("Save Output Image", icon=ft.icons.DOWNLOAD, bgcolor=ft.colors.GREEN_600, color=ft.colors.WHITE, on_click=lambda _: self.save_picker.save_file(file_name=self.get_output_filename()))
                    ], alignment=ft.MainAxisAlignment.CENTER)
                ]),
                expand=6,
                padding=15
            )
        ], expand=True)

    def on_slider_move(self, e):
        self.offset_x = self.offset_x_slider.value
        self.offset_y = self.offset_y_slider.value
        self.process_image(None)

    def on_image_pan(self, e: ft.DragUpdateEvent):
        zoom = float(self.zoom_slider.value)
        if zoom <= 1.0:
            return
        
        # Natural 1:1 drag physics scaling (counteracts zoom magnification)
        sensitivity = 0.008 / (zoom * zoom)
        
        self.offset_x = max(-1.0, min(1.0, self.offset_x - (e.delta_x * sensitivity)))
        self.offset_y = max(-1.0, min(1.0, self.offset_y - (e.delta_y * sensitivity)))
        
        # Keep sliders synced in real-time
        self.offset_x_slider.value = self.offset_x
        self.offset_y_slider.value = self.offset_y
        
        self.process_image(None)

    def get_output_filename(self):
        custom_name = self.filename_field.value.strip()
        fmt = self.format_dropdown.value.lower()
        if custom_name:
            if custom_name.lower().endswith(f".{fmt}"):
                return custom_name
            return f"{custom_name}.{fmt}"
        prefix = "signature" if self.is_signature else "photo"
        return f"{prefix}_formatted.{fmt}"    

    def on_preset_change(self, e):
        self.offset_x = 0.0 
        self.offset_y = 0.0
        self.offset_x_slider.value = 0.0
        self.offset_y_slider.value = 0.0
        if self.preset_dropdown.value == "Custom / Manual Settings":
            self.update()
            self.process_image(None)
            return

        preset = next((p for p in EXAM_PRESETS if p["examName"] == self.preset_dropdown.value), None)
        if preset:
            self.width_field.value = str(preset["width"])
            self.height_field.value = str(preset["height"])
            self.unit_dropdown.value = preset["unit"]
            self.min_kb_field.value = str(preset["minKb"])
            self.max_kb_field.value = str(preset["maxKb"])
            self.format_dropdown.value = preset["format"]
            
            self.update()
            self.process_image(None)

    def verify_preset_compliance(self):
        # Define preset_name first at the very top
        preset_name = self.preset_dropdown.value
        
        if not preset_name or preset_name == "Custom / Manual Settings":
            return True, ""
        
        preset = next((p for p in EXAM_PRESETS if p["examName"] == preset_name), None)
        if not preset:
            return True, ""

        mismatches = []
        try:
            if float(self.width_field.value) != float(preset["width"]):
                mismatches.append(f"Width ({self.width_field.value} vs req {preset['width']} {preset['unit']})")
            if float(self.height_field.value) != float(preset["height"]):
                mismatches.append(f"Height ({self.height_field.value} vs req {preset['height']} {preset['unit']})")
            if self.unit_dropdown.value != preset["unit"]:
                mismatches.append(f"Unit ({self.unit_dropdown.value} vs req {preset['unit']})")
            if int(self.min_kb_field.value) != int(preset["minKb"]):
                mismatches.append(f"Min KB ({self.min_kb_field.value} vs req {preset['minKb']} KB)")
            if int(self.max_kb_field.value) != int(preset["maxKb"]):
                mismatches.append(f"Max KB ({self.max_kb_field.value} vs req {preset['maxKb']} KB)")
            if self.format_dropdown.value.upper() != preset["format"].upper():
                mismatches.append(f"Format ({self.format_dropdown.value} vs req {preset['format']})")
        except ValueError:
            mismatches.append("Invalid numerical input")

        if mismatches:
            return False, f"✖ DOES NOT MATCH {preset_name.upper()}\nReason: {', '.join(mismatches)}"
        
        return True, f"✔ COMPLIANT WITH {preset_name.upper()}"

    def on_file_selected(self, e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            self.offset_x = 0.0 
            self.offset_y = 0.0
            self.offset_x_slider.value = 0.0
            self.offset_y_slider.value = 0.0
            with open(e.files[0].path, "rb") as f:
                self.raw_image_bytes = f.read()
            self.process_image(None)

    def process_image(self, e):
        if not self.raw_image_bytes:
            return

        if not self.is_signature:
            self.name_field.visible = self.banner_checkbox.value
            self.date_field.visible = self.banner_checkbox.value
            self.update()

        # Open image with PIL
        img = Image.open(io.BytesIO(self.raw_image_bytes)).convert("RGB")
        
        # 1. Zoom & Crop
        orig_w, orig_h = img.size
        zoom_level = float(self.zoom_slider.value)
        if zoom_level > 1.0:
            crop_w = orig_w / zoom_level
            crop_h = orig_h / zoom_level
            
            max_shift_x = (orig_w - crop_w) / 2
            max_shift_y = (orig_h - crop_h) / 2
            
            shift_x = self.offset_x * max_shift_x
            shift_y = self.offset_y * max_shift_y
            
            center_x = (orig_w / 2) + shift_x
            center_y = (orig_h / 2) + shift_y
            
            left = max(0, center_x - (crop_w / 2))
            top = max(0, center_y - (crop_h / 2))
            right = min(orig_w, left + crop_w)
            bottom = min(orig_h, top + crop_h)
            
            img = img.crop((left, top, right, bottom))
        else:
            self.offset_x = 0.0
            self.offset_y = 0.0

        # 2. Ink Enhancer on HIGH-RESOLUTION image FIRST (preserves smooth pen strokes!)
        if self.is_signature and self.ink_checkbox.value:
            threshold = int(self.threshold_slider.value)
            gray = img.convert("L")
            img = gray.point(lambda p: 255 if p > threshold else 0).convert("RGB")

        # 3. Calculate target dimensions
        target_w = to_pixels(self.width_field.value, self.unit_dropdown.value)
        target_h = to_pixels(self.height_field.value, self.unit_dropdown.value)
        
        if target_w > 0 and target_h > 0:
            self.preview_card.aspect_ratio = target_w / target_h

        # 4. Banner Overlay (for photos)
        if not self.is_signature and self.banner_checkbox.value:
            draw = ImageDraw.Draw(img)
            banner_h = int(img.height * 0.18)
            banner_top = img.height - banner_h
            
            draw.rectangle([(0, banner_top), (img.width, img.height)], fill="white")
            
            name_txt = self.name_field.value.strip()
            date_txt = self.date_field.value.strip()
            text_str = f"{name_txt}\n{date_txt}" if date_txt else name_txt
            
            if text_str.strip():
                font_size = max(14, int(banner_h * 0.32))
                try:
                    font = ImageFont.load_default(size=font_size)
                except TypeError:
                    try:
                        font = ImageFont.truetype("arial.ttf", font_size)
                    except Exception:
                        font = ImageFont.load_default()

                center_x = img.width / 2
                center_y = banner_top + (banner_h / 2)
                
                draw.multiline_text(
                    (center_x, center_y),
                    text_str,
                    fill="black",
                    font=font,
                    anchor="mm",
                    align="center"
                )

        # 5. Final Resize to Target Dimensions
        resized_img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

        # Signature Ink Enhancer (B&W Thresholding)
        if self.is_signature and self.ink_checkbox.value:
            threshold = int(self.threshold_slider.value)
            gray = resized_img.convert("L")
            resized_img = gray.point(lambda p: 255 if p > threshold else 0).convert("RGB")

        # Banner Overlay
        if not self.is_signature and self.banner_checkbox.value:
            draw = ImageDraw.Draw(resized_img)
            banner_h = int(target_h * 0.18)  # Clean 18% height banner
            banner_top = target_h - banner_h
            
            # Draw pure white banner
            draw.rectangle([(0, banner_top), (target_w, target_h)], fill="white")
            
            name_txt = self.name_field.value.strip()
            date_txt = self.date_field.value.strip()
            text_str = f"{name_txt}\n{date_txt}" if date_txt else name_txt
            
            if text_str.strip():
                # Auto-scale font size proportional to the banner height
                font_size = max(14, int(banner_h * 0.32))
                
                try:
                    font = ImageFont.load_default(size=font_size)
                except TypeError:
                    try:
                        font = ImageFont.truetype("arial.ttf", font_size)
                    except Exception:
                        font = ImageFont.load_default()

                # Center text perfectly horizontally and vertically
                center_x = target_w / 2
                center_y = banner_top + (banner_h / 2)
                
                draw.multiline_text(
                    (center_x, center_y),
                    text_str,
                    fill="black",
                    font=font,
                    anchor="mm",
                    align="center"
                )

        max_kb = int(self.max_kb_field.value or 50)
        min_kb = int(self.min_kb_field.value or 10)
        fmt = self.format_dropdown.value.upper()
        save_fmt = "PNG" if fmt == "PNG" else "JPEG"

        safe_target_kb = max(float(min_kb) + 1.0, float(max_kb) * 0.88)

        quality = 95
        buf = io.BytesIO()
        
        if save_fmt == "PNG":
            resized_img.save(buf, format="PNG", optimize=True)
            current_kb = len(buf.getvalue()) / 1024.0
            # Auto-pad PNG if too small
            if current_kb < min_kb:
                needed_bytes = int((min_kb + 2 - current_kb) * 1024)
                buf.write(b"\x00" * needed_bytes)
        else:
            resized_img.save(buf, format="JPEG", quality=quality)
            
            # Step 1: If TOO LARGE (> max_kb), lower quality to reduce size
            while (len(buf.getvalue()) / 1024.0) > safe_target_kb and quality > 5:
                quality -= 1
                buf = io.BytesIO()
                resized_img.save(buf, format="JPEG", quality=quality)

            # Step 2: If TOO SMALL (< min_kb), auto-pad with safe metadata to increase size
            current_kb = len(buf.getvalue()) / 1024.0
            if current_kb < min_kb:
                target_pad_kb = float(min_kb) + 2.0  # Aim for ~12 KB
                needed_bytes = int((target_pad_kb - current_kb) * 1024)
                buf = io.BytesIO()
                resized_img.save(buf, format="JPEG", quality=98, comment=b"0" * needed_bytes)
        self.processed_bytes = buf.getvalue()
        actual_kb = len(self.processed_bytes) / 1024.0

        # Verification Checks
        is_kb_compliant = min_kb <= actual_kb <= max_kb
        matches_preset, preset_status_msg = self.verify_preset_compliance()
        
        preset_name = self.preset_dropdown.value
        overall_compliant = is_kb_compliant and matches_preset

        if preset_name and preset_name != "Custom / Manual Settings":
            if not matches_preset:
                status_header = preset_status_msg
            else:
                status_header = preset_status_msg if is_kb_compliant else f"✖ NON-COMPLIANT WITH {preset_name.upper()} (File size out of range)"
        else:
            status_header = "✔ COMPLIANT WITH CUSTOM SETTINGS" if is_kb_compliant else "✖ NON-COMPLIANT WITH CUSTOM SETTINGS"

        dim_str = f"✔ Dimensions: {target_w} x {target_h} px ({self.width_field.value} x {self.height_field.value} {self.unit_dropdown.value})"
        size_str = f"{'✔' if is_kb_compliant else '✖'} File Size: {actual_kb:.2f} KB (Target: {min_kb}-{max_kb} KB)"
        fmt_str = f"✔ Format: {fmt}"

        self.compliance_text.value = f"{status_header}\n{dim_str}\n{size_str}\n{fmt_str}"
        self.compliance_container.bgcolor = ft.colors.GREEN_50 if overall_compliant else ft.colors.RED_50
        self.compliance_container.border = ft.border.all(1, ft.colors.GREEN if overall_compliant else ft.colors.RED)
        self.compliance_text.color = ft.colors.GREEN_800 if overall_compliant else ft.colors.RED_800

        base64_str = base64.b64encode(self.processed_bytes).decode('utf-8')
        self.image_preview.src_base64 = base64_str
        self.update()

    def on_save_location(self, e: ft.FilePickerResultEvent):
        if e.path and self.processed_bytes:
            with open(e.path, "wb") as f:
                f.write(self.processed_bytes)
            self.page.show_snack_bar(ft.SnackBar(content=ft.Text(f"Saved successfully to: {e.path}")))

def check_for_updates(page: ft.Page):
    if "YOUR_GITHUB_USERNAME" in REMOTE_VERSION_URL:
        return
    try:
        req = urllib.request.Request(REMOTE_VERSION_URL, headers={'User-Agent': 'GovDocFormatterApp/1.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                latest_ver = data.get("version", APP_VERSION)
                download_url = data.get("download_url", "")
                if latest_ver > APP_VERSION:
                    page.show_snack_bar(
                        ft.SnackBar(
                            content=ft.Text(f"🎉 New update v{latest_ver} is available!"),
                            action="View Update",
                            on_action=lambda _: page.launch_url(download_url),
                            duration=10000
                        )
                    )
    except Exception:
        pass

def main(page: ft.Page):
    page.title = "GovDoc Formatter & Resizer (Python)"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 10

    # Correct syntax for your Flet version
    page.window_minimized = False
    page.window_focused = True
    page.window_resizable = True

    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=300,
        tabs=[
            ft.Tab(text="Photo Workspace", icon=ft.icons.ACCOUNT_BOX, content=WorkspaceTab(is_signature=False)),
            ft.Tab(text="Signature Workspace", icon=ft.icons.DRAW, content=WorkspaceTab(is_signature=True)),
        ],
        expand=True
    )

    page.add(
        ft.AppBar(
            title=ft.Text("GovDoc Formatter & Resizer", color=ft.colors.WHITE, weight=ft.FontWeight.BOLD),
            bgcolor=ft.colors.BLUE_800,
            leading=ft.Icon(ft.icons.PHOTO_SIZE_SELECT_LARGE, color=ft.colors.WHITE),
        ),
        tabs
    )
    check_for_updates(page)

if __name__ == "__main__":
    ft.app(target=main)