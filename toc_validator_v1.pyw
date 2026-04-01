import sys
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import re
import csv
import unicodedata 
from collections import Counter

# ======================================================================
# AUTO-INSTALLER BOOTSTRAP
# ======================================================================

def check_and_launch():
    """Tries to import third-party packages. If missing, prompts the user to install them."""
    try:
        # Try to import PyMuPDF. If it fails, we trigger the installer.
        global fitz
        import fitz
        
        # If it succeeds, launch the app normally!
        launch_app()
    except ImportError:
        prompt_installation()

def prompt_installation():
    """Shows a UI prompting the user to install missing packages."""
    root = tk.Tk()
    root.withdraw() # Hide the empty main window
    
    msg = (
        "This application requires the 'PyMuPDF' package to read PDF files, "
        "but it is not installed on this computer.\n\n"
        "Would you like to automatically download and install it now?"
    )
    
    if messagebox.askyesno("Missing Package Required", msg):
        install_window = tk.Toplevel(root)
        install_window.title("Installing Dependencies")
        install_window.geometry("350x120")
        install_window.resizable(False, False)
        
        # Center the loading window on the screen
        install_window.update_idletasks()
        x = (install_window.winfo_screenwidth() // 2) - (350 // 2)
        y = (install_window.winfo_screenheight() // 2) - (120 // 2)
        install_window.geometry(f"+{x}+{y}")
        
        tk.Label(install_window, text="Installing PyMuPDF...\nPlease wait, this may take a minute.", pady=10).pack()
        
        progress = ttk.Progressbar(install_window, mode='indeterminate')
        progress.pack(fill='x', padx=20, pady=5)
        progress.start()
        
        def install_worker():
            try:
                # creationflags=0x08000000 ensures NO black command prompt window flashes on screen
                flags = 0x08000000 if sys.platform == "win32" else 0
                subprocess.run([sys.executable, "-m", "pip", "install", "PyMuPDF"],
                    check=True,
                    capture_output=True,
                    text=True,
                    creationflags=flags
                )
                # Success! Tell the main thread to wrap up.
                root.after(0, install_success, root, install_window)
            except subprocess.CalledProcessError as e:
                # Failed! Grab the error output.
                err = e.stderr or e.stdout or "Unknown error"
                root.after(0, install_failed, root, install_window, err)
                
        # Run the installation in the background so the UI doesn't freeze
        threading.Thread(target=install_worker, daemon=True).start()
        root.mainloop()
    else:
        root.destroy()
        sys.exit()

def install_success(root, install_window):
    install_window.destroy()
    messagebox.showinfo("Success", "Package installed successfully! The application will now start.")
    root.quit()
    root.destroy()
    
    # Import fitz now that it exists, then start the main app!
    global fitz
    import fitz
    launch_app()

def install_failed(root, install_window, err_msg):
    install_window.destroy()
    messagebox.showerror(
        "Installation Failed", 
        f"Failed to install PyMuPDF. IT policies might be blocking the installation.\n\nError details:\n{err_msg}"
    )
    root.quit()
    root.destroy()
    sys.exit()

def launch_app():
    """Starts the actual main application."""
    main_root = tk.Tk()
    app = TOCValidatorApp(main_root)
    main_root.mainloop()


# ======================================================================
# MAIN APPLICATION CODE
# ======================================================================

class TOCValidatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Textbook TOC Validator")
        self.root.geometry("1150x750")
        self.root.resizable(True, True)

        self.filepath = tk.StringVar()
        self.validation_results =[]

        self.setup_ui()

    def setup_ui(self):
        # Configuration Frame
        input_frame = ttk.LabelFrame(self.root, text="Configuration", padding=(10, 10))
        input_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(input_frame, text="PDF File:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(input_frame, textvariable=self.filepath, width=70, state="readonly").grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(input_frame, text="Browse", command=self.browse_file).grid(row=0, column=2, pady=5)

        ttk.Label(input_frame, text="TOC PDF Page Range (e.g. 5-7):").grid(row=1, column=0, sticky="w", pady=5)
        self.toc_range_entry = ttk.Entry(input_frame, width=15)
        self.toc_range_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(input_frame, text="PDF Page # for printed 'Page 1' (put '1' if no offset):").grid(row=2, column=0, sticky="w", pady=5)
        self.page1_entry = ttk.Entry(input_frame, width=15)
        self.page1_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        # Button and Progress Bar Frame
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=5, fill="x", padx=10)

        self.run_btn = ttk.Button(btn_frame, text="Validate Pagination", command=self.start_validation)
        self.run_btn.pack(side="left", padx=(0, 10))

        self.export_btn = ttk.Button(btn_frame, text="Export to CSV", command=self.export_csv, state="disabled")
        self.export_btn.pack(side="left", padx=10)

        # Progress Bar and Label
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(btn_frame, orient="horizontal", length=300, mode="determinate", variable=self.progress_var)
        self.progress_bar.pack(side="left", padx=10)

        self.progress_label = ttk.Label(btn_frame, text="0%")
        self.progress_label.pack(side="left", padx=5)

        # Results Frame
        results_frame = ttk.LabelFrame(self.root, text="Validation Results", padding=(10, 10))
        results_frame.pack(fill="both", expand=True, padx=10, pady=10)

        filter_frame = ttk.Frame(results_frame)
        filter_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(filter_frame, text="Filter View:").pack(side="left")
        self.filter_var = tk.StringVar(value="All")
        self.filter_cb = ttk.Combobox(filter_frame, textvariable=self.filter_var,
                                      values=["All", "Pass", "Fail", "Error"],
                                      state="readonly", width=15)
        self.filter_cb.pack(side="left", padx=10)
        self.filter_cb.bind("<<ComboboxSelected>>", self.apply_filter)

        self.log_text = tk.Text(results_frame, height=3, state="disabled", bg="#f0f0f0", fg="#333")
        self.log_text.pack(fill="x", pady=(0, 10))

        columns = ("chapter", "title", "printed", "pdf", "status")
        self.tree = ttk.Treeview(results_frame, columns=columns, show="headings")

        self.tree.heading("chapter", text="Chapter/Section",    command=lambda: self.sort_column("chapter", False))
        self.tree.heading("title",   text="Title",              command=lambda: self.sort_column("title", False))
        self.tree.heading("printed", text="Printed ToC Page",   command=lambda: self.sort_column("printed", False))
        self.tree.heading("pdf",     text="PDF Page",           command=lambda: self.sort_column("pdf", False))
        self.tree.heading("status",  text="Validation Status",  command=lambda: self.sort_column("status", False))

        self.tree.column("chapter", width=120, anchor="w")
        self.tree.column("title",   width=350, anchor="w")
        self.tree.column("printed", width=100, anchor="center")
        self.tree.column("pdf",     width=130, anchor="center")
        self.tree.column("status",  width=220, anchor="w")

        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.tree.tag_configure("PASS",  background="#d4edda", foreground="#155724")
        self.tree.tag_configure("FAIL",  background="#f8d7da", foreground="#721c24")
        self.tree.tag_configure("ERROR", background="#fff3cd", foreground="#856404")

    # ------------------------------------------------------------------
    def browse_file(self):
        file = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if file:
            self.filepath.set(file)

    def log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, "end")
        self.log_text.insert("end", message)
        self.log_text.configure(state="disabled")
        self.root.update_idletasks()

    def update_progress(self, value, text_status=""):
        self.progress_var.set(value)
        if text_status:
            self.progress_label.config(text=text_status)

    def sort_column(self, col, reverse):
        rows =[(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        try:
            rows.sort(key=lambda t: int(t[0]), reverse=reverse)
        except ValueError:
            rows.sort(reverse=reverse)
        for index, (_, k) in enumerate(rows):
            self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def apply_filter(self, event=None):
        for item in self.tree.get_children():
            self.tree.delete(item)

        selected_filter = self.filter_var.get().upper()

        for res in self.validation_results:
            status_text = res["Status"].upper()
            tag = "ERROR"
            if "PASS" in status_text:
                tag = "PASS"
            elif "FAIL" in status_text:
                tag = "FAIL"

            if selected_filter == "ALL" or selected_filter in status_text:
                self.tree.insert("", "end", values=(
                    res["Chapter/Sec"],
                    res["Title"],
                    res["Expected Printed Page"],
                    res["Calculated PDF Page"],
                    res["Status"]
                ), tags=(tag,))

    def start_validation(self):
        if not self.filepath.get():
            messagebox.showerror("Error", "Please select a PDF file.")
            return

        try:
            toc_range = self.toc_range_entry.get().split('-')
            self.toc_start = int(toc_range[0].strip()) - 1
            self.toc_end = int(toc_range[1].strip()) - 1 if len(toc_range) > 1 else self.toc_start
            self.page1_pdf_index = int(self.page1_entry.get().strip()) - 1
        except Exception:
            messagebox.showerror("Error", "Please enter valid numbers for the page ranges.")
            return

        self.run_btn.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        
        self.update_progress(0, "0%")
        self.validation_results =[]
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.log("Status: Extracting TOC Data from PDF...")
        threading.Thread(target=self.process_pdf, daemon=True).start()

    # ------------------------------------------------------------------
    def normalize_text(self, text, keep_spaces=False):
        if not text:
            return ""
        t = unicodedata.normalize('NFKC', str(text))
        t = t.lower()
        if keep_spaces:
            t = re.sub(r'[^\w\+=\s]', '', t)
            t = re.sub(r'\s+', ' ', t).strip()
        else:
            t = re.sub(r'[^\w\+=]', '', t)
        return t
    
    # ------------------------------------------------------------------
    def _clean_title(self, title):
        title = re.sub(r'^[•·▪◦|]+\s*', '', title)
        title = re.sub(r'^[-–—]+\s*', '', title)
        title = re.sub(r'[\ue000-\uf8ff]', '', title)
        title = re.sub(r'[\ufffd\u25a1\u25a0\u0000-\u001f]', '', title)
        title = re.sub(r'\s{2,}', ' ', title)
        return title.strip()

    # ------------------------------------------------------------------
    def _parse_candidate_string(self, candidate, matches, last_page):
        sub_entries = re.split(r'\s*[•·▪◦|]\s*', candidate)
        buffer_no_num = ""

        for sub_entry in sub_entries:
            sub_entry = sub_entry.strip()
            if not sub_entry:
                continue

            if buffer_no_num:
                sub_entry = buffer_no_num + " " + sub_entry
                buffer_no_num = ""

            page_match = re.search(r'(?:\.{2,}|\s+)(\d+)$', sub_entry)
            if page_match:
                candidate_page = int(page_match.group(1))
                is_real_page = False
                
                if re.search(r'(?:\.{2,}|\s{2,}|\t)\d+$', sub_entry):
                    is_real_page = True
                elif last_page == 0 or candidate_page >= last_page or (last_page - candidate_page) < 50:
                    is_real_page = True
                
                if is_real_page:
                    title_val = self._clean_title(sub_entry[:page_match.start()].strip())
                    if title_val:
                        matches.append((title_val, candidate_page))
                        last_page = candidate_page
                else:
                    buffer_no_num = sub_entry
            else:
                buffer_no_num = sub_entry

        if buffer_no_num:
            page_match = re.search(r'(?:\.{2,}|\s+)(\d+)$', buffer_no_num)
            if page_match:
                candidate_page = int(page_match.group(1))
                is_real_page = False
                
                if re.search(r'(?:\.{2,}|\s{2,}|\t)\d+$', buffer_no_num):
                    is_real_page = True
                elif last_page == 0 or candidate_page >= last_page or (last_page - candidate_page) < 50:
                    is_real_page = True
                    
                if is_real_page:
                    title_val = self._clean_title(buffer_no_num[:page_match.start()].strip())
                    if title_val:
                        matches.append((title_val, candidate_page))
                        last_page = candidate_page

        return last_page

    # ------------------------------------------------------------------
    def process_pdf(self):
        try:
            doc = fitz.open(self.filepath.get())
            total_pages = len(doc)
            matches =[]

            self.root.after(0, self.update_progress, 0, "Reading TOC...")
            last_page = 0 

            for page_num in range(self.toc_start, self.toc_end + 1):
                if page_num >= total_pages:
                    continue
                page        = doc[page_num]
                page_height = page.rect.height
                blocks = page.get_text("blocks", sort=True)

                for block in blocks:
                    if block[6] != 0:
                        continue
                        
                    y0, y1 = block[1], block[3]
                    if y0 < (page_height * 0.07) or y1 > (page_height * 0.93):
                        continue

                    block_text = block[4]
                    current_title_buffer = ""

                    for line in block_text.split('\n'):
                        line = line.strip()

                        if not line:
                            if current_title_buffer.strip():
                                last_page = self._parse_candidate_string(current_title_buffer.strip(), matches, last_page)
                                current_title_buffer = ""
                            continue

                        if ".indd" in line.lower() or ".pdf" in line.lower():
                            continue

                        if re.match(r'^\d+$', line):
                            candidate_page = int(line)
                            if last_page == 0 or candidate_page >= last_page or (last_page - candidate_page) < 50:
                                if current_title_buffer.strip():
                                    candidate = (current_title_buffer.strip() + " " + line).strip()
                                    last_page = self._parse_candidate_string(candidate, matches, last_page)
                                    current_title_buffer = ""
                                continue
                            else:
                                current_title_buffer += " " + line
                                continue

                        page_match = re.search(r'(?:\.{2,}|\s+)(\d+)$', line)

                        if page_match:
                            candidate_page = int(page_match.group(1))
                            is_real_page = False
                            
                            if re.search(r'(?:\.{2,}|\s{2,}|\t)\d+$', line):
                                is_real_page = True
                            elif last_page == 0 or candidate_page >= last_page or (last_page - candidate_page) < 50:
                                is_real_page = True
                                
                            if is_real_page:
                                candidate = (current_title_buffer + " " + line).strip()
                                last_page = self._parse_candidate_string(candidate, matches, last_page)
                                current_title_buffer = ""
                            else:
                                current_title_buffer += " " + line
                        else:
                            current_title_buffer += " " + line

                    if current_title_buffer.strip():
                        last_page = self._parse_candidate_string(current_title_buffer.strip(), matches, last_page)
                        current_title_buffer = ""

            if not matches:
                self.root.after(0, lambda: self.log("Error: Could not detect any TOC entries. Check ranges."))
                self.root.after(0, lambda: self.run_btn.configure(state="normal"))
                self.root.after(0, self.update_progress, 0, "0%")
                return

            total_matches = len(matches)
            self.root.after(0, lambda: self.log(f"Status: Found {total_matches} TOC entries. Validating pages..."))

            errors  = 0
            success = 0

            for i, (raw_title, printed_page) in enumerate(matches):
                target_pdf_page = (printed_page - 1) + self.page1_pdf_index
                status = ""

                prefix_pattern = r'^((?:chapter|appendix|part|module|unit|section)\s+[a-zA-Z0-9\.\-]+|[0-9]+(?:\.[0-9]+)*)[\s:\-–—\.]+'
                match = re.search(prefix_pattern, raw_title, flags=re.IGNORECASE)
                
                if match:
                    chapter_sec = match.group(1).strip()
                    clean_title = raw_title[match.end():].strip()
                    if not clean_title:
                        clean_title = raw_title
                else:
                    chapter_sec = ""
                    clean_title = raw_title

                if target_pdf_page >= total_pages or target_pdf_page < 0:
                    status = "ERROR (Out of Bounds)"
                    errors += 1
                else:
                    page      = doc[target_pdf_page]
                    page_dict = page.get_text("dict", sort=True)

                    font_sizes  = []
                    text_spans  =[]

                    for blk in page_dict.get("blocks",[]):
                        if blk.get("type") == 0:
                            for ln in blk.get("lines",[]):
                                for span in ln.get("spans",[]):
                                    text = span.get("text", "").strip()
                                    if text:
                                        size    = round(span.get("size", 0), 1)
                                        is_bold = "bold" in span.get("font", "").lower()
                                        font_sizes.extend([size] * len(text))
                                        text_spans.append({"text": text, "size": size, "bold": is_bold})

                    body_size = Counter(font_sizes).most_common(1)[0][0] if font_sizes else 0

                    full_text_raw    = " ".join(s["text"] for s in text_spans)
                    heading_text_raw = " ".join(
                        s["text"] for s in text_spans
                        if s["size"] > body_size + 0.4 or s["bold"]
                    )

                    full_text_clean    = self.normalize_text(full_text_raw)
                    heading_text_clean = self.normalize_text(heading_text_raw)
                    toc_clean          = self.normalize_text(raw_title)
                    toc_clean_no_pre   = self.normalize_text(clean_title)

                    if toc_clean in heading_text_clean or (toc_clean_no_pre and toc_clean_no_pre in heading_text_clean):
                        status = "PASS (Heading Match)"
                        success += 1
                    elif toc_clean in full_text_clean or (toc_clean_no_pre and toc_clean_no_pre in full_text_clean):
                        status = "PASS (Exact Body Match)"
                        success += 1
                    else:
                        toc_words     = self.normalize_text(clean_title, keep_spaces=True).split()
                        heading_words = set(self.normalize_text(heading_text_raw, keep_spaces=True).split())
                        body_words    = set(self.normalize_text(full_text_raw, keep_spaces=True).split())

                        if toc_words and all(tw in heading_words for tw in toc_words):
                            status = "PASS (Unordered Heading Match)"
                            success += 1
                        elif toc_words and all(tw in body_words for tw in toc_words):
                            status = "PASS (Unordered Body Match)"
                            success += 1
                        else:
                            status = "FAIL (Not Found)"
                            errors += 1

                row_data = {
                    "Chapter/Sec":          chapter_sec,
                    "Title":                clean_title,
                    "Expected Printed Page": printed_page,
                    "Calculated PDF Page":  target_pdf_page + 1,
                    "Status":               status
                }
                self.validation_results.append(row_data)

                percent_complete = ((i + 1) / total_matches) * 100
                progress_text = f"{int(percent_complete)}% ({i+1}/{total_matches})"
                self.root.after(0, self.update_progress, percent_complete, progress_text)

            self.validation_results.sort(key=lambda x: x["Expected Printed Page"])

            self.root.after(0, self.apply_filter)
            self.root.after(0, lambda: self.log(
                f"Validation Complete! Passed: {success} | Failed/Errors: {errors}"
            ))
            self.root.after(0, self.update_progress, 100, "Done!")

        except Exception as e:
            self.root.after(0, lambda: self.log(f"An error occurred: {str(e)}"))
            self.root.after(0, self.update_progress, 0, "Error")
        finally:
            self.root.after(0, lambda: self.run_btn.configure(state="normal"))
            if self.validation_results:
                self.root.after(0, lambda: self.export_btn.configure(state="normal"))

    # ------------------------------------------------------------------
    def export_csv(self):
        if not self.validation_results:
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            title="Save Results As"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "Chapter/Sec", "Title", "Expected Printed Page",
                    "Calculated PDF Page", "Status"
                ])
                writer.writeheader()
                for res in self.validation_results:
                    writer.writerow(res)
            messagebox.showinfo("Success", f"Results exported successfully to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save CSV:\n{str(e)}")


if __name__ == "__main__":
    # pass app to the bootstrapper first!
    check_and_launch()