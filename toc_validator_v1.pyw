import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import fitz  # PyMuPDF
import re
import threading
import csv

# look at header (just in case toc title text is in body text of that page)
# there might be sub sub headers (account for them)
# 
class TOCValidatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Textbook TOC Validator")
        self.root.geometry("950x750")
        self.root.resizable(True, True)

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
        ttk.Entry(input_frame, textvariable=self.filepath, width=60, state="readonly").grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(input_frame, text="Browse", command=self.browse_file).grid(row=0, column=2, pady=5)

        # TOC Pages
        ttk.Label(input_frame, text="TOC PDF Page Range (e.g. 5-7):").grid(row=1, column=0, sticky="w", pady=5)
        self.toc_range_entry = ttk.Entry(input_frame, width=15)
        self.toc_range_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        # Page 1 Offset
        ttk.Label(input_frame, text="PDF Page # for printed 'Page 1' (put 1 if no page offset):").grid(row=2, column=0, sticky="w", pady=5)
        self.page1_entry = ttk.Entry(input_frame, width=15)
        self.page1_entry.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        # Buttons Frame
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=10)

        self.run_btn = ttk.Button(btn_frame, text="Validate Pagination", command=self.start_validation)
        self.run_btn.pack(side="left", padx=10)

        self.export_btn = ttk.Button(btn_frame, text="Export to CSV", command=self.export_csv, state="disabled")
        self.export_btn.pack(side="left", padx=10)

        # Output Log
        log_frame = ttk.LabelFrame(self.root, text="Validation Results", padding=(10, 10))
        log_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_text = tk.Text(log_frame, wrap="word", height=15, state="disabled")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def browse_file(self):
        file = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if file:
            self.filepath.set(file)

    def log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def start_validation(self):
        if not self.filepath.get():
            messagebox.showerror("Error", "Please select a PDF file.")
            return
            
        try:
            toc_range = self.toc_range_entry.get().split('-')
            self.toc_start = int(toc_range[0].strip()) - 1 # PyMuPDF is 0-indexed
            self.toc_end = int(toc_range[1].strip()) - 1 if len(toc_range) > 1 else self.toc_start
            
            self.page1_pdf_index = int(self.page1_entry.get().strip()) - 1
        except Exception:
            messagebox.showerror("Error", "Please enter valid numbers for the page ranges.")
            return

        self.run_btn.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self.validation_results =[]
        self.log_text.configure(state="normal")
        self.log_text.delete(1.0, "end")
        self.log_text.configure(state="disabled")
        self.log("Starting validation...\n")

        # Run processing in a separate thread so GUI doesn't freeze
        threading.Thread(target=self.process_pdf, daemon=True).start()

    def process_pdf(self):
        try:
            doc = fitz.open(self.filepath.get())
            total_pages = len(doc)
            matches =[]

            # 1. Extract TOC text using Document Blocks 
            for page_num in range(self.toc_start, self.toc_end + 1):
                if page_num >= total_pages:
                    continue
                
                page = doc[page_num]
                page_height = page.rect.height
                blocks = page.get_text("blocks")
                
                for block in blocks:
                    # Ignore images/drawings (block type 0 is text)
                    if block[6] != 0:
                        continue
                    
                    # Ignore Headers and Footers based on physical coordinates (top 7% and bottom 7% of page)
                    y0, y1 = block[1], block[3]
                    if y0 < (page_height * 0.07) or y1 > (page_height * 0.93):
                        continue

                    block_text = block[4]
                    current_title_buffer = ""
                    
                    for line in block_text.split('\n'):
                        line = line.strip()
                        if not line:
                            continue

                        # Explicitly ignore publisher draft files/watermarks
                        if ".indd" in line.lower() or ".pdf" in line.lower():
                            continue

                        # Check if line is JUST a number (sometimes page numbers get pushed to a new line)
                        if re.match(r'^\d+$', line):
                            if current_title_buffer.strip():
                                matches.append((current_title_buffer.strip(), int(line)))
                                current_title_buffer = ""
                            continue

                        # Check if line ends with a page number using regex
                        # First try: dots or wide spacing then any page number
                        page_match = re.search(r'(?:\.{2,}\s*|\s{2,})(\d+)$', line)
                        # Fallback: single space only for 2+ digit page numbers
                        # (avoids treating things like "Math Essential 1" as page 1)
                        if not page_match:
                            page_match = re.search(r'\s(\d{2,})$', line)
                        
                        if page_match:
                            page_num_val = page_match.group(1)
                            rest_of_line = line[:page_match.start()].strip()
                            
                            full_title = (current_title_buffer + " " + rest_of_line).strip()
                            if full_title: # Avoid empty entries
                                matches.append((full_title, int(page_num_val)))
                            
                            # Clear the buffer for the next entry
                            current_title_buffer = ""
                        else:
                            # Multi-line title: Add to buffer
                            current_title_buffer += " " + line

                    # After processing all lines in this block, flush any remaining
                    # buffer as a no-page-number entry
                    if current_title_buffer.strip():
                        matches.append((current_title_buffer.strip(), None))
                        current_title_buffer = ""

            if not matches:
                self.log("Could not detect any TOC entries. Ensure the TOC pages are correct.")
                self.run_btn.configure(state="normal")
                return

            self.log(f"Found {len(matches)} TOC entries. Validating...\n")
            self.log("-" * 75)

            errors = 0
            success = 0
            no_page = 0

            # 2. Validate each entry
            for title, printed_page in matches:
                # Handle TOC entries that had no page number
                if printed_page is None:
                    self.log(f"[INFO] '{title}' -> No page number listed in TOC.")
                    self.validation_results.append({
                        "Chapter Title": title, "Expected Printed Page": "N/A",
                        "Calculated PDF Page": "N/A", "Status": "No Page Number"
                    })
                    no_page += 1
                    continue

                target_pdf_page = (printed_page - 1) + self.page1_pdf_index

                if target_pdf_page >= total_pages or target_pdf_page < 0:
                    self.log(f"[ERROR] '{title}' -> PDF Page {target_pdf_page+1} is out of bounds!")
                    self.validation_results.append({
                        "Chapter Title": title, "Expected Printed Page": printed_page,
                        "Calculated PDF Page": target_pdf_page+1, "Status": "FAIL (Out of Bounds)"
                    })
                    errors += 1
                    continue

                # Extract text from the destination page to verify
                target_text = doc[target_pdf_page].get_text("text").lower()
                
                # Split title into words and strip punctuation
                raw_words = title.split()
                clean_words =[re.sub(r'^\W+|\W+$', '', w).lower() for w in raw_words]
                
                # We want to check for significant words (length > 3) OR chapter numbers (like "1.2" or "4")
                search_words =[w for w in clean_words if len(w) > 3 or re.match(r'^\d+(?:\.\d+)*$', w)]
                
                if not search_words:
                    search_words = [title.lower()]

                # Check if at least some significant words/chapter numbers from the title are on the target page
                matches_found = sum(1 for word in search_words if word in target_text)
                
                if matches_found > 0 or not search_words:
                    self.log(f"[PASS] '{title}' -> Found on PDF Page {target_pdf_page+1}.")
                    self.validation_results.append({
                        "Chapter Title": title, "Expected Printed Page": printed_page,
                        "Calculated PDF Page": target_pdf_page+1, "Status": "PASS"
                    })
                    success += 1
                else:
                    self.log(f"[FAIL] '{title}' -> Text not found on PDF Page {target_pdf_page+1}. Pagination may be offset.")
                    self.validation_results.append({
                        "Chapter Title": title, "Expected Printed Page": printed_page,
                        "Calculated PDF Page": target_pdf_page+1, "Status": "FAIL (Mismatch)"
                    })
                    errors += 1

            self.log("-" * 75)
            self.log(f"Validation Complete! Passed: {success} | Failed: {errors} | No Page Number: {no_page}")

        except Exception as e:
            self.log(f"\nAn error occurred: {str(e)}")
        finally:
            self.run_btn.configure(state="normal")
            if self.validation_results:
                self.export_btn.configure(state="normal")

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