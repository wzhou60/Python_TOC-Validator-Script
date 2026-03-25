import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import fitz  # PyMuPDF
import re
import threading
import csv
from collections import Counter

class TOCValidatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Textbook TOC Validator (Exact Match & Inline Headings)")
        self.root.geometry("950x700")
        self.root.resizable(False, False)

        # File selection & Data
        self.filepath = tk.StringVar()
        self.validation_results =[]
        
        # UI Setup
        self.setup_ui()

    def setup_ui(self):
        # Frame for inputs
        input_frame = ttk.LabelFrame(self.root, text="Configuration", padding=(10, 10))
        input_frame.pack(fill="x", padx=10, pady=10)

        # File browser
        ttk.Label(input_frame, text="PDF File:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(input_frame, textvariable=self.filepath, width=70, state="readonly").grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(input_frame, text="Browse", command=self.browse_file).grid(row=0, column=2, pady=5)

        # TOC Pages
        ttk.Label(input_frame, text="TOC PDF Page Range (e.g. 5-7):").grid(row=1, column=0, sticky="w", pady=5)
        self.toc_range_entry = ttk.Entry(input_frame, width=15)
        self.toc_range_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        # Page 1 Offset
        ttk.Label(input_frame, text="PDF Page # for printed 'Page 1':").grid(row=2, column=0, sticky="w", pady=5)
        self.page1_entry = ttk.Entry(input_frame, width=15)
        self.page1_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        # Buttons Frame
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=5)

        self.run_btn = ttk.Button(btn_frame, text="Validate Pagination", command=self.start_validation)
        self.run_btn.pack(side="left", padx=10)

        self.export_btn = ttk.Button(btn_frame, text="Export to CSV", command=self.export_csv, state="disabled")
        self.export_btn.pack(side="left", padx=10)

        # Results Area (Table + Filter + Small Log)
        results_frame = ttk.LabelFrame(self.root, text="Validation Results", padding=(10, 10))
        results_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Filter Dropdown
        filter_frame = ttk.Frame(results_frame)
        filter_frame.pack(fill="x", pady=(0, 5))
        
        ttk.Label(filter_frame, text="Filter View:").pack(side="left")
        self.filter_var = tk.StringVar(value="All")
        self.filter_cb = ttk.Combobox(filter_frame, textvariable=self.filter_var, values=["All", "Pass", "Fail", "Error"], state="readonly", width=15)
        self.filter_cb.pack(side="left", padx=10)
        self.filter_cb.bind("<<ComboboxSelected>>", self.apply_filter)
        
        # System Log (small text area for progress updates)
        self.log_text = tk.Text(results_frame, height=3, state="disabled", bg="#f0f0f0", fg="#333")
        self.log_text.pack(fill="x", pady=(0, 10))

        # Data Table (Treeview)
        columns = ("title", "printed", "pdf", "status")
        self.tree = ttk.Treeview(results_frame, columns=columns, show="headings")
        
        # Define headers and bind the sorting function to clicks
        self.tree.heading("title", text="Chapter Title", command=lambda: self.sort_column("title", False))
        self.tree.heading("printed", text="Printed Page", command=lambda: self.sort_column("printed", False))
        self.tree.heading("pdf", text="Calculated PDF Page", command=lambda: self.sort_column("pdf", False))
        self.tree.heading("status", text="Validation Status", command=lambda: self.sort_column("status", False))

        # Define column widths
        self.tree.column("title", width=400, anchor="w")
        self.tree.column("printed", width=100, anchor="center")
        self.tree.column("pdf", width=130, anchor="center")
        self.tree.column("status", width=200, anchor="w")

        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Define Color Tags for rows
        self.tree.tag_configure("PASS", background="#d4edda", foreground="#155724")
        self.tree.tag_configure("FAIL", background="#f8d7da", foreground="#721c24")
        self.tree.tag_configure("ERROR", background="#fff3cd", foreground="#856404")

    def browse_file(self):
        file = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if file:
            self.filepath.set(file)

    def log(self, message):
        """Updates the small progress text box."""
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, "end")
        self.log_text.insert("end", message)
        self.log_text.configure(state="disabled")
        self.root.update_idletasks()

    def sort_column(self, col, reverse):
        """Sorts the table columns when clicked."""
        l =[(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        try:
            l.sort(key=lambda t: int(t[0]), reverse=reverse)
        except ValueError:
            l.sort(reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def apply_filter(self, event=None):
        """Filters the table based on the dropdown selection and applies colors."""
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        selected_filter = self.filter_var.get().upper()
        
        for res in self.validation_results:
            status_text = res["Status"].upper()
            
            # Determine color tag
            tag = "ERROR"
            if "PASS" in status_text:
                tag = "PASS"
            elif "FAIL" in status_text:
                tag = "FAIL"

            if selected_filter == "ALL" or selected_filter in status_text:
                self.tree.insert("", "end", values=(
                    res["Chapter Title"], 
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
        self.validation_results =[]
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        self.log("Status: Extracting TOC Data from PDF...")
        threading.Thread(target=self.process_pdf, daemon=True).start()

    def normalize_text(self, text):
        t = text.replace('-\n', '').replace('- ', '')
        t = re.sub(r'[^\w\s]', ' ', t.lower())
        return re.sub(r'\s+', ' ', t).strip()

    def _parse_candidate_string(self, candidate, matches):
        """Breaks apart buffered lines to detect multiple inline headings separated by bullets/dots."""
        # Split the string using bullet points, middle dots, or pipes as separators
        sub_entries = re.split(r'\s*[•·▪◦|]\s*', candidate)
        
        buffer_no_num = ""
        
        for sub_entry in sub_entries:
            sub_entry = sub_entry.strip()
            if not sub_entry: continue
            
            # If a previous split didn't contain a number, it was likely a false split 
            # (a bullet in the middle of a title). Stitch it back together!
            if buffer_no_num:
                sub_entry = buffer_no_num + " • " + sub_entry
                buffer_no_num = ""
                
            page_match = re.search(r'(?:\.{2,}|\s+)(\d+)$', sub_entry)
            if page_match:
                page_val = int(page_match.group(1))
                title_val = sub_entry[:page_match.start()].strip()
                if title_val:
                    matches.append((title_val, page_val))
            else:
                # If we split and this part doesn't have a number, hold onto it
                buffer_no_num = sub_entry
                
        # Edge case: If the final part of the string didn't have a number, but it was passed in
        if buffer_no_num:
            page_match = re.search(r'(?:\.{2,}|\s+)(\d+)$', buffer_no_num)
            if page_match:
                matches.append((buffer_no_num[:page_match.start()].strip(), int(page_match.group(1))))

    def process_pdf(self):
        try:
            doc = fitz.open(self.filepath.get())
            total_pages = len(doc)
            matches =[]

            for page_num in range(self.toc_start, self.toc_end + 1):
                if page_num >= total_pages: continue
                page = doc[page_num]
                page_height = page.rect.height
                blocks = page.get_text("blocks")
                
                for block in blocks:
                    if block[6] != 0: continue 
                    y0, y1 = block[1], block[3]
                    if y0 < (page_height * 0.07) or y1 > (page_height * 0.93): continue

                    block_text = block[4]
                    current_title_buffer = ""
                    
                    for line in block_text.split('\n'):
                        line = line.strip()
                        if not line: continue
                        if ".indd" in line.lower() or ".pdf" in line.lower(): continue

                        if re.match(r'^\d+$', line):
                            if current_title_buffer.strip():
                                candidate = (current_title_buffer.strip() + " " + line).strip()
                                self._parse_candidate_string(candidate, matches)
                                current_title_buffer = ""
                            continue

                        page_match = re.search(r'(?:\.{2,}|\s+)(\d+)$', line)
                        if page_match:
                            candidate = (current_title_buffer + " " + line).strip()
                            self._parse_candidate_string(candidate, matches)
                            current_title_buffer = ""
                        else:
                            current_title_buffer += " " + line

            if not matches:
                self.root.after(0, lambda: self.log("Error: Could not detect any TOC entries. Check ranges."))
                self.root.after(0, lambda: self.run_btn.configure(state="normal"))
                return

            self.root.after(0, lambda: self.log(f"Status: Found {len(matches)} TOC entries. Validating pages..."))
            
            errors = 0
            success = 0

            for title, printed_page in matches:
                target_pdf_page = (printed_page - 1) + self.page1_pdf_index
                status = ""

                if target_pdf_page >= total_pages or target_pdf_page < 0:
                    status = "ERROR (Out of Bounds)"
                    errors += 1
                else:
                    page = doc[target_pdf_page]
                    page_dict = page.get_text("dict")
                    page_height = page.rect.height
                    
                    font_sizes =[]
                    text_spans =[]

                    for block in page_dict.get("blocks",[]):
                        if block.get("type") == 0:
                            y0, y1 = block["bbox"][1], block["bbox"][3]
                            if y0 < (page_height * 0.07) or y1 > (page_height * 0.93):
                                continue
                            
                            for line in block.get("lines",[]):
                                for span in line.get("spans",[]):
                                    text = span.get("text", "").strip()
                                    if text:
                                        size = round(span.get("size", 0), 1)
                                        is_bold = "bold" in span.get("font", "").lower()
                                        font_sizes.extend([size] * len(text))
                                        text_spans.append({"text": text, "size": size, "bold": is_bold})

                    body_size = Counter(font_sizes).most_common(1)[0][0] if font_sizes else 0

                    full_text_raw = " ".join([s["text"] for s in text_spans])
                    heading_text_raw = " ".join([s["text"] for s in text_spans if s["size"] > body_size + 0.4 or s["bold"]])

                    full_text_clean = self.normalize_text(full_text_raw)
                    heading_text_clean = self.normalize_text(heading_text_raw)
                    
                    toc_clean = self.normalize_text(title)
                    toc_no_nums = self.normalize_text(re.sub(r'^[\d\.\s]+', '', title))

                    if toc_clean in heading_text_clean or (toc_no_nums and toc_no_nums in heading_text_clean):
                        status = "PASS (Heading Match)"
                        success += 1
                    elif toc_clean in full_text_clean or (toc_no_nums and toc_no_nums in full_text_clean):
                        status = "PASS (Exact Body Match)"
                        success += 1
                    else:
                        status = "FAIL (Not Found)"
                        errors += 1

                row_data = {
                    "Chapter Title": title, 
                    "Expected Printed Page": printed_page,
                    "Calculated PDF Page": target_pdf_page+1, 
                    "Status": status
                }
                self.validation_results.append(row_data)

            self.root.after(0, self.apply_filter)
            self.root.after(0, lambda: self.log(f"Validation Complete! Passed: {success} | Failed/Errors: {errors}"))

        except Exception as e:
            self.root.after(0, lambda: self.log(f"An error occurred: {str(e)}"))
        finally:
            self.root.after(0, lambda: self.run_btn.configure(state="normal"))
            if self.validation_results:
                self.root.after(0, lambda: self.export_btn.configure(state="normal"))

    def export_csv(self):
        if not self.validation_results: return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv")],
            title="Save Results As"
        )
        if not file_path: return

        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=["Chapter Title", "Expected Printed Page", "Calculated PDF Page", "Status"])
                writer.writeheader()
                for res in self.validation_results:
                    writer.writerow(res)
            messagebox.showinfo("Success", f"Results exported successfully to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save CSV:\n{str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = TOCValidatorApp(root)
    root.mainloop()