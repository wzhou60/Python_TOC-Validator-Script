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
        self.root.geometry("1050x750")
        self.root.resizable(True, True)

        self.filepath = tk.StringVar()
        self.validation_results = []

        self.setup_ui()

    def setup_ui(self):
        # just setting up the UI stuff
        input_frame = ttk.LabelFrame(self.root, text="Configuration", padding=(10, 10))
        input_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(input_frame, text="PDF File:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(input_frame, textvariable=self.filepath, width=70, state="readonly").grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(input_frame, text="Browse", command=self.browse_file).grid(row=0, column=2, pady=5)

        ttk.Label(input_frame, text="TOC PDF Page Range (e.g. 5-7):").grid(row=1, column=0, sticky="w", pady=5)
        self.toc_range_entry = ttk.Entry(input_frame, width=15)
        self.toc_range_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(input_frame, text="PDF Page # for printed 'Page 1':").grid(row=2, column=0, sticky="w", pady=5)
        self.page1_entry = ttk.Entry(input_frame, width=15)
        self.page1_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=5)

        self.run_btn = ttk.Button(btn_frame, text="Validate Pagination", command=self.start_validation)
        self.run_btn.pack(side="left", padx=10)

        self.export_btn = ttk.Button(btn_frame, text="Export to CSV", command=self.export_csv, state="disabled")
        self.export_btn.pack(side="left", padx=10)

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

        columns = ("title", "printed", "pdf", "status")
        self.tree = ttk.Treeview(results_frame, columns=columns, show="headings")

        self.tree.heading("title",   text="Chapter Title",          command=lambda: self.sort_column("title", False))
        self.tree.heading("printed", text="Printed ToC Page",       command=lambda: self.sort_column("printed", False))
        self.tree.heading("pdf",     text="Calculated PDF Page",    command=lambda: self.sort_column("pdf", False))
        self.tree.heading("status",  text="Validation Status",      command=lambda: self.sort_column("status", False))

        self.tree.column("title",   width=400, anchor="w")
        self.tree.column("printed", width=100, anchor="center")
        self.tree.column("pdf",     width=130, anchor="center")
        self.tree.column("status",  width=200, anchor="w")

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

    def sort_column(self, col, reverse):
        rows = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
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
        self.validation_results = []
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.log("Status: Extracting TOC Data from PDF...")
        threading.Thread(target=self.process_pdf, daemon=True).start()

    # ------------------------------------------------------------------
    #         Corrected escape sequences in all regex patterns.
    #         Previously used r'\\s+' (raw string + double backslash) which
    #         matches a literal '\s', not whitespace.  Now uses r'\s+'.
    # ------------------------------------------------------------------
    def normalize_text(self, text):
        # Step 1: Join hard line-break hyphens 
        t = re.sub(r'-\s*\n\s*', ' ', text)
        
        # Step 2: Normalize ALL hyphens/en-dashes/em-dashes to a plain space so that for example: "Many-Electron", "Many- Electron", "Many — Electron" all become "Many Electron"
        t = re.sub(r'[-–—]', ' ', t)
        
        # Step 3: Strip remaining non-word characters and lowercase
        t = re.sub(r'[^\w\s]', ' ', t.lower())
        
        # Step 4: Collapse whitespace
        return re.sub(r'\s+', ' ', t).strip()
    
    # ------------------------------------------------------------------
    #      Strip leading bullet symbols from a title produced by splitting
    #      on bullet separators (e.g., "• WHEN OUR..." → "WHEN OUR...").
    # ------------------------------------------------------------------
    def _clean_title(self, title):
        # Strip leading bullet/separator symbols
        title = re.sub(r'^[•·▪◦|]+\s*', '', title)
        
        # FIX 2: Strip leading hyphens/dashes that bleed in from wrapped PDF lines
        title = re.sub(r'^[-–—]+\s*', '', title)
        
        # FIX 1: Remove Private Use Area characters (Wingdings etc.) that render as □
        # These are Unicode codepoints U+E000–U+F8FF (basic), U+F0000+ (supplementary)
        title = re.sub(r'[\ue000-\uf8ff]', '', title)
        
        # Also remove other common non-printable/replacement characters
        title = re.sub(r'[\ufffd\u25a1\u25a0\u0000-\u001f]', '', title)
        
        # Collapse any double spaces left behind
        title = re.sub(r'\s{2,}', ' ', title)
        return title.strip()

    # ------------------------------------------------------------------
    # IMPROVED _parse_candidate_string
    #   • FIX 2: Correct regex (r'...' with single backslash).
    #   • FIX 3: Use _clean_title() to strip leading bullet chars.
    #   • FIX 4: Stitch with a plain space instead of " • " so the bullet doesn't pollute the recovered title text.
    # ------------------------------------------------------------------
    def _parse_candidate_string(self, candidate, matches):
        """
        Splits a buffered TOC string on bullet separators (•, ·, ▪, ◦, |)
        to extract multiple inline entries that may share a single text line.

        Handles cases such as:
            NAIVE REALISM: IS SEEING BELIEVING? 7 • WHEN OUR COMMON SENSE IS RIGHT 8
        """
        sub_entries = re.split(r'\s*[•·▪◦|]\s*', candidate)
        buffer_no_num = ""

        for sub_entry in sub_entries:
            sub_entry = sub_entry.strip()
            if not sub_entry:
                continue

            # FIX 4: stitch with a plain space, not " • "
            if buffer_no_num:
                sub_entry = buffer_no_num + " " + sub_entry
                buffer_no_num = ""

            # FIX 2: corrected regex — r'\.{2,}' for dot leaders, r'\s+' for space
            page_match = re.search(r'(?:\.{2,}|\s+)(\d+)$', sub_entry)
            if page_match:
                page_val  = int(page_match.group(1))
                title_val = self._clean_title(sub_entry[:page_match.start()].strip())
                if title_val:
                    matches.append((title_val, page_val))
            else:
                # No page number yet — this split segment is a partial title;
                # hold it until the next segment supplies the page number.
                buffer_no_num = sub_entry

        # FIX 5: flush any leftover buffer (handles final segment with a page number)
        if buffer_no_num:
            page_match = re.search(r'(?:\.{2,}|\s+)(\d+)$', buffer_no_num)
            if page_match:
                title_val = self._clean_title(buffer_no_num[:page_match.start()].strip())
                if title_val:
                    matches.append((title_val, int(page_match.group(1))))

    # ------------------------------------------------------------------
    #   • Corrected page-number regex (single backslash).
    #   • Flush the title buffer at the END of every block so
    #            the last entry in a block is never silently dropped.
    #   • Empty lines within a block also trigger a buffer flush,
    #            preventing two separate entries from merging together.
    # ------------------------------------------------------------------
    def process_pdf(self):
        try:
            doc = fitz.open(self.filepath.get())
            total_pages = len(doc)
            matches = []

            for page_num in range(self.toc_start, self.toc_end + 1):
                if page_num >= total_pages:
                    continue
                page        = doc[page_num]
                page_height = page.rect.height
                blocks      = page.get_text("blocks")

                for block in blocks:
                    if block[6] != 0:
                        continue
                    y0, y1 = block[1], block[3]
                    if y0 < (page_height * 0.07) or y1 > (page_height * 0.93):
                        continue

                    block_text         = block[4]
                    current_title_buffer = ""

                    for line in block_text.split('\n'):
                        line = line.strip()

                        # blank line inside a block = entry boundary, flush buffer
                        if not line:
                            if current_title_buffer.strip():
                                self._parse_candidate_string(current_title_buffer.strip(), matches)
                                current_title_buffer = ""
                            continue

                        if ".indd" in line.lower() or ".pdf" in line.lower():
                            continue

                        # Standalone page number orphaned on its own line
                        if re.match(r'^\d+$', line):
                            if current_title_buffer.strip():
                                candidate = (current_title_buffer.strip() + " " + line).strip()
                                self._parse_candidate_string(candidate, matches)
                                current_title_buffer = ""
                            continue

                        #  corrected regex for trailing page number
                        page_match = re.search(r'(?:\.{2,}|\s+)(\d+)$', line)

                        if page_match:
                            # Line ends with a page number — complete entry (or group of entries)
                            candidate = (current_title_buffer + " " + line).strip()
                            self._parse_candidate_string(candidate, matches)
                            current_title_buffer = ""
                        else:
                            # No trailing number yet — could be a wrapped continuation
                            # (e.g., "NAIVE REALISM: IS SEEING BELIEVING? 7 • WHEN OUR")
                            current_title_buffer += " " + line

                    # FX 7: flush whatever remains at the END of each block
                    if current_title_buffer.strip():
                        self._parse_candidate_string(current_title_buffer.strip(), matches)
                        current_title_buffer = ""

            if not matches:
                self.root.after(0, lambda: self.log("Error: Could not detect any TOC entries. Check ranges."))
                self.root.after(0, lambda: self.run_btn.configure(state="normal"))
                return

            self.root.after(0, lambda: self.log(f"Status: Found {len(matches)} TOC entries. Validating pages..."))

            errors  = 0
            success = 0

            for title, printed_page in matches:
                target_pdf_page = (printed_page - 1) + self.page1_pdf_index
                status = ""

                if target_pdf_page >= total_pages or target_pdf_page < 0:
                    status = "ERROR (Out of Bounds)"
                    errors += 1
                else:
                    page      = doc[target_pdf_page]
                    page_dict = page.get_text("dict")
                    page_height = page.rect.height

                    font_sizes  = []
                    text_spans  = []

                    for blk in page_dict.get("blocks", []):
                        if blk.get("type") == 0:
                            y0, y1 = blk["bbox"][1], blk["bbox"][3]
                            if y0 < (page_height * 0.05) or y1 > (page_height * 0.95):
                                continue
                            for ln in blk.get("lines", []):
                                for span in ln.get("spans", []):
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

                    toc_clean = self.normalize_text(title)

                    # Strip any leading section number (e.g. "1.1 " or "1 ") before matching,
                    # so sub-headings like "1.1 What Is Psychology?" also match the page heading.
                    # FIX: corrected regex r'^[\d.\s]+' (was r'^[\\d\\.\\s]+')
                    toc_no_nums = self.normalize_text(re.sub(r'^[\d.\s]+', '', title))

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
                    "Chapter Title":        title,
                    "Expected Printed Page": printed_page,
                    "Calculated PDF Page":  target_pdf_page + 1,
                    "Status":               status
                }
                self.validation_results.append(row_data)

            self.root.after(0, self.apply_filter)
            self.root.after(0, lambda: self.log(
                f"Validation Complete! Passed: {success} | Failed/Errors: {errors}"
            ))

        except Exception as e:
            self.root.after(0, lambda: self.log(f"An error occurred: {str(e)}"))
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
                    "Chapter Title", "Expected Printed Page",
                    "Calculated PDF Page", "Status"
                ])
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
