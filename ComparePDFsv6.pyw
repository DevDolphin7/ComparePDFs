import configparser, logging, traceback, threading, os, sys, io, random, pytesseract, spacy
from dat import dat_main as data_main
from tkinter import Tk, Canvas, Button, filedialog, messagebox, StringVar, Label, Entry, IntVar, Toplevel, Radiobutton, Scale, Text
from tkinter.ttk import Progressbar
from PIL import Image, ImageTk
from pdf2image import convert_from_path
from difflib import Differ, SequenceMatcher

# Set paths for local OCR
pytesseract.pytesseract.tesseract_cmd = r'.\Tesseract-OCR\tesseract'
os.environ["PATH"] += os.pathsep + os.pathsep.join([".\\poppler-23.07.0\\Library\\bin"])

class GenerateUI():
    def __init__(self):
        # Log activity
        log_exc("App started", level=20)
        # Create window
        self.root = Tk()
        self.root.geometry("480x480")
        self.root.config(bg='white')
        self.root.title("PDF Comparator: A Dolphin Creation!")
        self.root.iconbitmap('./dat/CMicon.ico')
        self.root.resizable(False,False)

        # Handle Tkinter Errors
        self.root.report_callback_exception = self.reportCallbackException

        # Set class variables
        self.config_file_path = "./config.ini"
        self.help_file_path = "./Help.txt"
        self.pdf_files = {'old': '', 'new': ''}
        self.file_selected = {'old': False, 'new': False}
        self.num_pages = {}
        self.compare_thread = None
        self.dat = data_main.Data()
        self.crop_area_vars = {}
        self.crop_area_margins = {}

        # Initiate comparePDFs class
        self.comparePDFs = ComparePDFs()
        
        # User default class variables - load from config, set to default if not possible.
        if not self.loadConfig():
            self.file_types = (('Portable Document Format','*.pdf'),('All files','*.*'))
            self.init_dir = "./Examples/"
            self.output_dir = "./Comparisons/"
            self.user_crop_area = [0,8,0,8]
            self.open_result = True
            self.comparePDFs.page_similarity_threshold = 0.9
            self.comparePDFs.text_similarity_threshold = 0.95
            self.comparePDFs.text_comparison_accuracy = False # <-- False = Fast, True = Slow but more accurate

        # Set the crop area else now else it won't update for preview functionality prior to settings window openning
        self.comparePDFs.desired_crop = self.user_crop_area

        # Create Bg and UI
        self.createBg()
        self.createUI()

        self.updateStatus()        
        self.root.mainloop()


    def reportCallbackException(self, *args):
        err = traceback.format_exception(*args)
        if err[len(err)-1][:54] == '_tkinter.TclError: invalid command name ".!progressbar':
            self.startCompare(tknoerr=False)
        else:
            # Tkinter has thrown an unknown error
            error_msg = ""
            for item in err:
                error_msg += item
            log_exc(f'Unknown Tk Exception', level=40)
            raise Exception(f'Tk Exception: {error_msg}')


    def loadConfig(self):
        config = configparser.ConfigParser()

        try:
            config.read(self.config_file_path)

            # Load variables
            self.file_types = tuple(tuple(map(str.strip, tpl.strip('()').split(','))) for tpl in config.get('Settings', 'File Types').split('|'))
            self.init_dir = str(config.get('Settings', 'Inital Directory'))
            self.output_dir = str(config.get('Settings', 'Output Directory'))
            self.user_crop_area = list(map(int, config.get('Settings', 'Crop Area').split(',')))
            if config.get('Settings', 'Open Output on Completion') == "False": self.open_result = False
            else: self.open_result = True
            self.comparePDFs.page_similarity_threshold = float(config.get('Tuning', 'Page Similarity Threshold'))
            self.comparePDFs.text_similarity_threshold = float(config.get('Tuning', 'Text Similarity Threshold'))
            if config.get('Tuning', 'Text Comparison Accuracy') == "False": self.comparePDFs.text_comparison_accuracy = False
            else: self.comparePDFs.text_comparison_accuracy = True
            
            return True
        
        except Exception as e:
            log_exc(f"Error loading configuration file 'config.ini'")
            messagebox.showinfo("Configuration Error Occured", f"Error loading configuration file 'config.ini'.\n\nTo prevent this in the future, navigate to Settings and click Save As Default.")
            return False


    def createBg(self):
        # Load bg image from .py files
        b = bytearray(self.dat.data("CMbg"))
        self.bgPicImg = Image.open(io.BytesIO(b))
        self.bgPic = ImageTk.PhotoImage(image=self.bgPicImg)

        # Set bg pic as window bg
        self.canvas = Canvas(self.root, width=480, height=480)
        self.bg_container = self.canvas.create_image(240,240,image=self.bgPic)
        self.canvas.pack(fill="both",expand=True)        


    def createUI(self):
        # Create labels for current selected file
        self.old_file_text = StringVar()
        self.old_file_label = Label(self.root,textvariable=self.old_file_text, anchor="e")
        self.canvas.create_window(20, 20, anchor="nw", window=self.old_file_label, width=170, height=30)
        self.new_file_text = StringVar()
        self.new_file_label = Label(self.root,textvariable=self.new_file_text, anchor="e")
        self.canvas.create_window(20, 60, anchor="nw", window=self.new_file_label, width=170, height=30)

        # Create buttons to select a file
        self.open_old_file_button = Button(self.root, text="Select Old PDF",command=lambda: self.selectFile('old'))
        self.canvas.create_window(200, 20, anchor="nw", window=self.open_old_file_button, width=100, height=30)
        self.open_new_file_button = Button(self.root,text="Select New PDF",command=lambda: self.selectFile('new'))
        self.canvas.create_window(200, 60, anchor="nw", window=self.open_new_file_button, width=100, height=30)

        # Create preview, settings and compare buttons
        self.preview_button = Button(self.root,text="Preview", bg="light blue",command=self.showPreview, state='normal')
        self.canvas.create_window(310, 20, anchor="nw", window=self.preview_button, width=60,height=30)
        self.settings_button = Button(self.root,text="Settings", bg="light grey",command=self.popupSettings)
        self.canvas.create_window(310, 60, anchor="nw", window=self.settings_button, width=60,height=30) 
        self.convert_button = Button(self.root,text="Compare", bg="red",command=self.startCompare)
        self.canvas.create_window(380, 20, anchor="nw", window=self.convert_button, width=80,height=70)

        # Bundle all user editable items in a list to allow easy disable / enable during processing
        self.main_window_ui_items = [self.open_old_file_button,self.open_new_file_button,self.preview_button,self.settings_button,self.convert_button]


    def createPleaseWait(self):
        self.please_wait_label = Label(self.root,text="Please wait, loading...", fg='red')
        self.canvas.create_window(330, 430, anchor="nw", window=self.please_wait_label, width=150, height=50)
        self.root.update()


    def removePleaseWait(self):
        self.please_wait_label.destroy()
        self.root.update()


    def createProgressBar(self):
        self.num_pages_total = int(self.num_pages['old']) + int(self.num_pages['new'])
        self.progress = Progressbar(self.root, orient='horizontal', mode='determinate')
        self.canvas.create_window(0, 455, anchor="nw", window=self.progress, width=480, height=25)
        self.root.update()


    def updateProgressBar(self):
        active_page = self.comparePDFs.current_page
        progress = int(((active_page - 1) / (1.2 * self.num_pages_total)) * 100)
        self.progress['value'] = progress
        
        self.root.update_idletasks()
        if not self.compare_thread.is_alive():
            self.root.after(1000, self.removeProgressBar)
        else:
            self.compare_seconds += 1
            self.root.after(1000, self.updateProgressBar)


    def removeProgressBar(self):
        self.comparePDFs.current_page = 1
        self.progress.destroy()
        
        # Log time taken to load file
        log_exc(f"Took {self.compare_seconds} seconds to compare {self.pdf_files['old']} to {self.pdf_files['new']}", level=20)
        
        self.root.update()
        self.compare_thread.join()

    
    def selectFile(self,file_num):
        self.select_file_num = file_num
        # Get file path from user
        select_file = filedialog.askopenfilename(title='Select a PDF file',
                                                 initialdir=self.init_dir,
                                                 filetypes=self.file_types)

        # If file path doesn't exist exit function
        if select_file == "":
            log_exc("Aborted file selection window with no file selected.", level=20)
            return None

        # Set file path in variables
        self.file_selected[file_num] = True
        self.pdf_files[file_num] = select_file

        # Create please wait comment
        self.createPleaseWait()

        # Load images
        self.loading_pdf_seconds = 0
        self.load_pdf_thread = threading.Thread(target=self.startLoadPdfThread)
        self.load_pdf_thread.start()
        self.checkPdfLoadingStatus()

        # Set initial file directory
        self.init_dir = select_file[0:select_file.rfind("/")+1]
        

    def startLoadPdfThread(self):
        # Disable buttons during loading the pdfs
        try:
            self.enableDisableButtons('disabled')
            self.num_pages[self.select_file_num] = self.comparePDFs.loadPDFs(self.pdf_files[self.select_file_num], self.select_file_num)
        except Exception as e:
            log_exc(f"An unkown error occured while loading the pdf {select_file}", level=40)
            messagebox.showinfo(title='Error Occured',message=f"An error occured while loading {select_file}\n\nError info: {e}")
        finally: self.enableDisableButtons('normal')


    def checkPdfLoadingStatus(self):
        if self.load_pdf_thread.is_alive():
            self.loading_pdf_seconds += 1
            self.root.after(1000, self.checkPdfLoadingStatus)
        else:
            # Remove please wait comment
            self.removePleaseWait()

            # Log time taken to load file
            log_exc(f"Took {self.loading_pdf_seconds} seconds to load {self.pdf_files[self.select_file_num]}", level=20)
            
            # Finish loading threads
            self.root.update()
            self.load_pdf_thread.join()
            self.updateStatus()
        

    def selectOutputFilePath(self):
        file_names = {}
        for key, path in self.pdf_files.items():
            if len(self.pdf_files[key][path.rfind("/")+1:]) > 40: file_names[key] = self.pdf_files[key][(len(path)-40):-4]
            else: file_names[key] = self.pdf_files[key][path.rfind("/")+1:-4]

        select_saveasfile = filedialog.asksaveasfile(title='Select a folder and name for the output file',
                                                     initialfile=f"Differences {file_names['old']} to {file_names['new']}",
                                                     initialdir=self.output_dir,
                                                     defaultextension=".txt",
                                                     filetypes=[("All Files","*.*"),("Text Documents","*.txt")])

        # If file path doesn't exist exit function
        if select_saveasfile == None:
            log_exc("Compare button ran with no directory selected - compare aborted.", level=20)
            return False
        else:
            output_path = select_saveasfile.name
            self.comparePDFs.output_path = output_path
            self.output_dir = output_path[0:output_path.rfind("/")+1]
            return True


    def showPreview(self):
        self.updateStatus()
        self.comparePDFs.previewPDF()

    def popupSettings(self):
        # Create settings window
        self.settings_root = Toplevel(self.root)
        self.settings_root.geometry("740x480")
        self.settings_root.config(bg='red')
        self.settings_root.title("PDF Comparator Settings")
        self.settings_root.iconbitmap('./dat/CMicon.ico')
        self.settings_root.resizable(False, False)

        # Create settings bg
        self.settings_canvas = Canvas(self.settings_root)
        self.settings_canvas.pack(fill="both",expand=True)
        self.settings_canvas.bind_all('<ButtonRelease-1>',self.updateStatus)
        self.settings_canvas.bind_all('<Key>',self.updateStatus)
        
        # Create crop area adjustment boxes
        label_text_lists = [['Left 0-49%','Top 0-49%'], ['Right 0-49%', 'Bottom 0-49%']]
        for i in range(0,2):
            if i == 0:
                self.crop_area_setup = ["self.crop_LH_width_",
                                        "self.crop_LH_height_"]

            else:
                self.crop_area_setup = ["self.crop_RH_width_",
                                        "self.crop_RH_height_"]

            for count, item in enumerate(self.crop_area_setup):
                self.crop_area_vars[f'{item}var'] = IntVar(self.settings_root)
                self.crop_area_vars[f'{item}entry'] = Entry(self.settings_root)
                entry_width = (count * 160) + 135
                entry_height = (i*50)+20
                self.settings_canvas.create_window(entry_width, entry_height, anchor="nw", window=self.crop_area_vars[f'{item}entry'],
                                          width=25, height=25)

                # Create labels for crop area inputs
                label_text = label_text_lists[i][count]
                self.crop_area_vars[f'{item}labels'] = Label(self.settings_root,text=label_text,bg="light blue")
                label_width = (count * 160) + 20
                label_height = (i*50)+20
                self.settings_canvas.create_window(label_width, label_height, anchor="nw", window=self.crop_area_vars[f'{item}labels'],
                                          width=105, height=25)                

        # Reset crop area for updateStatus function
        self.crop_area_setup = ["self.crop_LH_width_",
                                "self.crop_LH_height_",
                                "self.crop_RH_width_",
                                "self.crop_RH_height_"]

        # Set initial values to users current settings
        for count, item in enumerate(self.crop_area_setup):
            self.crop_area_vars[f'{item}var'].set(self.user_crop_area[count])
            self.crop_area_vars[f'{item}entry'].insert(0,self.user_crop_area[count])
        
        # Create portrait or landscape radiobutton choice
        self.portrait_landscape_selection = StringVar()
        self.portrait_radio = Radiobutton(self.settings_root, text="Portrait", variable=self.portrait_landscape_selection, value="portrait", command=self.updateStatus)
        self.settings_canvas.create_window(20, 115, anchor="nw", window=self.portrait_radio, width=95, height=25)
        self.landscape_radio = Radiobutton(self.settings_root, text="Landscape", variable=self.portrait_landscape_selection, value="landscape", command=self.updateStatus)
        self.settings_canvas.create_window(130, 115, anchor="nw", window=self.landscape_radio, width=95, height=25)
        self.portrait_landscape_selection.set("portrait")

        # Create demo and margins rectangles
        self.demo_rectangle = self.settings_canvas.create_rectangle(1,2,3,4, fill="black") # <-- Coordinates changed in updateStatus function anyway 
        for item in self.crop_area_setup:
            self.crop_area_margins[f'{item}margin'] = self.settings_canvas.create_rectangle(1,2,3,4,fill="orange") # <-- Coordinates and colours changed in updateStatus function anyway

        # Create sliders for similarity thresholds
        self.page_threshold_label = Label(self.settings_root,text="Page similarity threshold ratio:", anchor="w")
        self.settings_canvas.create_window(420, 20, anchor="nw", window=self.page_threshold_label, width=170, height=25)
        self.page_threshold_scale = Scale(self.settings_root, from_=0, to=1, tickinterval=0.1, length=300, orient="horizontal", resolution=0.01)
        self.settings_canvas.create_window(420, 40, anchor="nw", window=self.page_threshold_scale, width=300, height=55)
        self.page_threshold_scale.set(self.comparePDFs.page_similarity_threshold)

        self.text_threshold_label = Label(self.settings_root,text="Text similarity threshold ratio:", anchor="w")
        self.settings_canvas.create_window(420, 140, anchor="nw", window=self.text_threshold_label, width=170, height=25)
        self.text_threshold_scale = Scale(self.settings_root, from_=0, to=1, tickinterval=0.1, length=300, orient="horizontal", resolution=0.01)
        self.settings_canvas.create_window(420, 160, anchor="nw", window=self.text_threshold_scale, width=300, height=55)
        self.text_threshold_scale.set(self.comparePDFs.text_similarity_threshold)
        
        # Create boolean radiobuttons for accuracy setting. StringVar used to record settings in output.
        self.fast_accurate_label = Label(self.settings_root,text="Text comparison accuracy:", anchor="w")
        self.settings_canvas.create_window(420, 280, anchor="nw", window=self.fast_accurate_label, width=170, height=25)
        
        self.fast_accurate_selection = StringVar()
        self.fast_radio = Radiobutton(self.settings_root, text="Fast", variable=self.fast_accurate_selection, value=False, command=self.updateStatus)
        self.settings_canvas.create_window(420, 305, anchor="nw", window=self.fast_radio, width=95, height=25)
        self.accurate_radio = Radiobutton(self.settings_root, text="Accurate", variable=self.fast_accurate_selection, value=True, command=self.updateStatus)
        self.settings_canvas.create_window(520, 305, anchor="nw", window=self.accurate_radio, width=95, height=25)
        if self.comparePDFs.text_comparison_accuracy: self.fast_accurate_selection.set(1)
        else: self.fast_accurate_selection.set(0)

        # Create boolean radiobuttons for open output after completion. StringVar used to record settings in output.
        self.open_output_label = Label(self.settings_root,text="Open output document on completion:", anchor="w")
        self.settings_canvas.create_window(420, 350, anchor="nw", window=self.open_output_label, width=250, height=25)
        
        self.open_output_selection = StringVar()
        self.open_radio = Radiobutton(self.settings_root, text="Yes", variable=self.open_output_selection, value=True, command=self.updateStatus)
        self.settings_canvas.create_window(420, 375, anchor="nw", window=self.open_radio, width=95, height=25)
        self.close_radio = Radiobutton(self.settings_root, text="No", variable=self.open_output_selection, value=False, command=self.updateStatus)
        self.settings_canvas.create_window(520, 375, anchor="nw", window=self.close_radio, width=95, height=25)
        if self.open_result: self.open_output_selection.set(1)
        else: self.open_output_selection.set(0)

        # Create apply, save and help buttons. Also create a blank label that can be updated if settings are saved.
        self.apply_button = Button(self.settings_root,text="Apply", command=self.updateStatus)
        self.settings_canvas.create_window(420, 430, anchor="nw", window=self.apply_button, width=60,height=30)
        self.save_button = Button(self.settings_root,text="Save As Default", bg="light blue",command=self.saveConfig)
        self.settings_canvas.create_window(540, 430, anchor="nw", window=self.save_button, width=100,height=30)
        self.save_label_text = StringVar()
        self.save_label = Label(self.settings_root,textvariable=self.save_label_text, fg="red")
        self.settings_canvas.create_window(540, 405, anchor="nw", window=self.save_label, width=100, height=25)
        self.help_button = Button(self.settings_root,text="Help", bg="light blue",command=self.showHelp)
        self.settings_canvas.create_window(660, 430, anchor="nw", window=self.help_button, width=60,height=30)

        # Bundle all user editable items in settings into a list to allow easy disable / enable during processing
        self.settings_window_ui_items = [self.portrait_radio,
                                         self.landscape_radio,
                                         self.page_threshold_scale,
                                         self.text_threshold_scale,
                                         self.fast_radio,
                                         self.accurate_radio,
                                         self.open_radio,
                                         self.close_radio,
                                         self.apply_button,
                                         self.save_button,
                                         self.help_button]
        for item in self.crop_area_setup:
            self.settings_window_ui_items.append(self.crop_area_vars[f'{item}entry'])
        
        
        # Update status after settings initialised
        self.updateStatus()


    def saveConfig(self, *event):
        config = configparser.ConfigParser()
        config['User Information'] = {'Top': "This is the config file for the ComparePDFs applicaiton writted by a dolphin.",
                                      'General': "The values of this config file can be manually adjusted below or most can be altered through the Settings menu. Makes sure you click Save As Default!",
                                      'Information': "If for any reason the app cannot load these values, it defaults to the values defined in the source code. It will inform you if it does this.",
                                      'Warning': "Manual editing is encouraged but may lead to errors. See 'Help.txt' to reset config.ini if this is the case.",
                                      'Further Help': "For further help navigate to the settings menu and click the 'Help' button or see 'Help.txt'."}
        config['Settings'] = {'File Types': '|'.join([f'({name},{pattern})' for name, pattern in self.file_types]),
                              'Inital Directory': self.init_dir,
                              'Output Directory': self.output_dir,
                              'Crop Area': ','.join(map(str, self.user_crop_area)),
                              'Open Output on Completion': self.open_result}
        config['Tuning'] = {'Page Similarity Threshold': self.comparePDFs.page_similarity_threshold,
                            'Text Similarity Threshold': self.comparePDFs.text_similarity_threshold,
                            'Text Comparison Accuracy': self.comparePDFs.text_comparison_accuracy}

        try:
            with OpenFile(self.config_file_path,config=True) as config_file:
                config.write(config_file)
            # Update user of sucess
            self.save_label_text.set("Saved!")
            return True
        except Exception as e:
            # Update user about error
            log_exc(f"Error saving configuration file 'config.ini'")
            messagebox.showinfo("Configuration Error Occured",f"Error saving configuration file 'config.ini'.\n\nError information: {e}")
            self.save_label_text.set("Save error")
            return False


    def showHelp(self, *event):
        with open(self.help_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        f.close()

        self.help_root = Toplevel()
        self.help_root.title("PDF Comparator Help")
        self.help_root.geometry("1000x700")
        self.help_root.iconbitmap('./dat/CMicon.ico')

        text_widget = Text(self.help_root, wrap="word")
        text_widget.insert("end", content)
        text_widget.config(state='disabled')

        text_widget.pack(expand=True, fill='both')         


    def startCompare(self, tknoerr=True):
        if not(self.file_selected['old'] and self.file_selected['new']):
            log_exc("Compare button ran with no file selected.", level=20)
            if check_consecutive_errors(look_for="Compare button ran with no file selected."):
                messagebox.showinfo(title='Warning',message="Warning: No file selected!")
            return
        
        # If progress bar exists, compare button has already been clicked! Throughs error if more than 1 at a time.
        try:
            if tknoerr:
                self.progress['value'] = 0
                return
        except AttributeError: pass

        # Set output path
        output_path_selected = self.selectOutputFilePath()
        if not output_path_selected: return

        self.comparePDFs.pdf_file_paths = self.pdf_files
        
        # Create progress bar
        self.createProgressBar()

        # Compare PDFs
        self.compare_seconds = 0
        self.compare_thread = threading.Thread(target=self.startCompareThread)
        self.compare_thread.start()
        self.updateProgressBar()
        

    def startCompareThread(self):
        try:
            self.enableDisableButtons('disabled')
            self.comparePDFs.extractTextFromPdfs()
            self.comparePDFs.alignPagesOnContent()
            self.comparePDFs.comparePdfs()
            output_success = self.comparePDFs.documentDiffs()
            if output_success and self.open_result:
                os.startfile(self.comparePDFs.output_path)
        except Exception as e:
            log_exc("An unkown error occured while comparing the documents in a 2nd thread", level=40)
            messagebox.showinfo(title='Error Occured',message=f"Error: {e}")
        finally: self.enableDisableButtons('normal')
        

    def enableDisableButtons(self,state):      
        for var in self.main_window_ui_items:
            var['state'] = state

        # See if settings window has been created or is currently active.
        try:
            if Toplevel.winfo_exists(self.settings_root) == 0: return
        except AttributeError: return

        for var in self.settings_window_ui_items:
            var['state'] = state
        

    def updateStatus(self,*event):
        # Update path text
        self.old_file_text.set(self.pdf_files['old'])
        self.new_file_text.set(self.pdf_files['new'])

        # Update file selected
        for key, value in self.pdf_files.items():
            if value == "":
                self.file_selected[key] = False
            else:
                self.file_selected[key] = True

        # Update convert button
        if self.file_selected['old'] and self.file_selected['new']: self.convert_button.config(bg="green")
        else: self.convert_button.config(bg="red")

        # See if settings window has been created or is currently active.
        try:
            if Toplevel.winfo_exists(self.settings_root) == 0: return
        except AttributeError: return
        
        # From settings window, update crop area
        for count, item in enumerate(self.crop_area_setup):
            user_input = self.crop_area_vars[f'{item}entry'].get()
            
            if user_input == "":
                # If value is blank, make it 0
                self.crop_area_vars[f'{item}entry'].insert(0,"0")
                user_input = 0
            
            try:
                user_input = int(user_input)
                if user_input > 49: 1/0
                if user_input < 0: 1/0
            except:
                # If user's input is not a number, warn and reset to 0
                log_exc("Settings value error in crop area: The value entered into the crop area must be an integer between 0% - 49%. Input was reset.", level=20)
                if check_consecutive_errors(look_for="Settings value error in crop area:"):
                    messagebox.showinfo(title='Information',message="The value entered into the crop area must be an integer between 0% - 49%. Resetting input...")
                self.crop_area_vars[f'{item}entry'].delete(0,len(str(user_input)))
                self.crop_area_vars[f'{item}entry'].insert(0,"0")
                user_input = 0
        
            self.user_crop_area[count] = user_input

        # In settings window, update demo rectangle and margins
        if self.portrait_landscape_selection.get() == "portrait":
            demo_rectangle_geometry = [20, 160, 230, 460]
            margin_geometry = [20,160,(20+(2.1*int(self.crop_area_vars[f'{self.crop_area_setup[0]}entry'].get()))),460, # <-- left margin coords
                               20, 160, 230, (160+(3*int(self.crop_area_vars[f'{self.crop_area_setup[1]}entry'].get()))), # <-- top margin coords
                               (230-(2.1*int(self.crop_area_vars[f'{self.crop_area_setup[2]}entry'].get()))),160,230,460, # <-- right margin coords
                               20,(460-(3*int(self.crop_area_vars[f'{self.crop_area_setup[3]}entry'].get()))),230,460] # <-- bottom margin coords
        else:
            demo_rectangle_geometry = [20, 160, 320, 370]
            margin_geometry = [20,160,(20+(3*int(self.crop_area_vars[f'{self.crop_area_setup[0]}entry'].get()))),370, # <-- left margin coords
                               20, 160, 320, (160+(2.1*int(self.crop_area_vars[f'{self.crop_area_setup[1]}entry'].get()))), # <-- top margin coords
                               (320-(3*int(self.crop_area_vars[f'{self.crop_area_setup[2]}entry'].get()))),160,320,370, # <-- right margin coords
                               20,(370-(2.1*int(self.crop_area_vars[f'{self.crop_area_setup[3]}entry'].get()))),320,370] # <-- bottom margin coords

        self.settings_canvas.coords(self.demo_rectangle,demo_rectangle_geometry[0],demo_rectangle_geometry[1],demo_rectangle_geometry[2],demo_rectangle_geometry[3])

        # In settings window, update margin rectangles in settings
        for count, item in enumerate(self.crop_area_setup):
            mgin_count = count * 4
            self.settings_canvas.coords(self.crop_area_margins[f'{item}margin'],margin_geometry[mgin_count],margin_geometry[mgin_count+1],margin_geometry[mgin_count+2],margin_geometry[mgin_count+3])
            if self.user_crop_area[count] == 0: self.settings_canvas.itemconfig(self.crop_area_margins[f'{item}margin'], fill="", outline="")
            else: self.settings_canvas.itemconfig(self.crop_area_margins[f'{item}margin'], fill="orange", outline="orange")

        # In settings window, update values from sliders in settings
        self.comparePDFs.page_similarity_threshold = self.page_threshold_scale.get()
        self.comparePDFs.text_similarity_threshold = self.text_threshold_scale.get()

        # In settings window, update fast / accurate choice
        if self.fast_accurate_selection.get() == "0": self.comparePDFs.text_comparison_accuracy = False
        else: self.comparePDFs.text_comparison_accuracy = True

        # In settings window, update open output on completion choice
        if self.open_output_selection.get() == "1": self.open_result = True
        else: self.open_result = False
        
        # Pass the crop area to comparePDFs
        self.comparePDFs.desired_crop = self.user_crop_area

        # Bring the settings window infront of the main window
        self.settings_root.lift()
        try: self.help_root.lift()
        except: pass





class ComparePDFs():
    def __init__(self):
        # Class variables
        self.output_path = "./Differences.txt"
        self.pdf_file_paths = {}
        self.pdf_images = {}
        self.all_text = {}
        self.current_page = 1
        self.desired_crop = [0,0,0,0]
        self.page_size = ()
        self.page_similarity_threshold = 0
        self.text_similarity_threshold = 0
        self.text_comparison_accuracy = False


    def loadPDFs(self, path, file_num):
        try:
            self.pdf_images[file_num] = convert_from_path(path)
            num_pages = len(self.pdf_images[file_num])
            return num_pages
        except Exception as e:
            log_exc("An unknown error occured while loading the PDF images")
            messagebox.showinfo(title='Error Occured',message=f"Error: {e}")
            

    def previewPDF(self):
        try_files = ['old', 'new']

        # Make sure a file has been loaded
        if len(self.pdf_images) == 0:
            log_exc("Preview button ran with no file selected.", level=20)
            if check_consecutive_errors(look_for="Preview button ran with no file selected."):
                messagebox.showinfo(title='Warning',message="Warning: No file selected!")
            return

        # Find a file that has been loaded
        for var in try_files:
            try:
                self.pdf_images[var]
                a_loaded_file = var
            except: pass

        # Load a random page and apply the crop area for the preview
        page = random.randint(0,len(self.pdf_images[a_loaded_file])-1)
        image = self.pdf_images[a_loaded_file][page]
        self.page_size = image.size
        self.setCropArea()
        image.crop(self.crop_area).show()


    def setCropArea(self):
        left_margin = int(self.page_size[0] * (self.desired_crop[0] / 100))
        top_margin = int(self.page_size[1] * (self.desired_crop[1] / 100))
        right_margin = int(self.page_size[0] * (self.desired_crop[2] / 100))
        bottom_margin = int(self.page_size[1] * (self.desired_crop[3] / 100))

        right_margin = self.page_size[0] - right_margin
        bottom_margin = self.page_size[1] - bottom_margin

        self.crop_area = tuple([left_margin,top_margin,right_margin,bottom_margin])

         
    def extractTextFromPdfs(self):
        text = {}
        
        # Perform OCR on each image and extract text
        for file_num, page_images in self.pdf_images.items():
            for page_num, image in enumerate(page_images, 1):
                # Define crop area for each image (if pages are different sizes then crop area is different)
                if not image.size == self.page_size:
                    self.page_size = image.size
                    self.setCropArea()
                image_cropped = image.crop(self.crop_area)

                # Extract text from the page
                text[page_num] = pytesseract.image_to_string(image_cropped)

                self.current_page += 1
            # Assigning the text to the all_text dict seems to have an issue with overwriting the 'old' value unless exec is used.
            exec(f"self.all_text['{file_num}'] = {text}")

        self.reconstruct_sentences()

    def reconstruct_sentences(self):       
        nlp = spacy.load("en_core_web_sm")
        sentences = {}
        
        for file in self.all_text.keys():
            sentences[file] = {}
            for page_num, page_text in self.all_text[file].items():
                # Extract sentences from the SpaCy Doc object
                doc = nlp(page_text)
                list_of_sentences = [sent.text.replace("\n"," ").replace("  "," ")+"\n" for sent in doc.sents]
                print(f"\n\n list of sentences:\n{list_of_sentences}\n\n")
                
                page_text = "".join(f"{sentance}" for sentance in list_of_sentences)
                sentences[file][page_num] = page_text

        self.all_text = sentences


    def alignPagesOnContent(self):
        self.aligned_pages = []

        text1 = self.all_text['old']
        text2 = self.all_text['new']

        # First pass of page alignment, comparing new doc to old doc
        for page_num1, page_text1 in text1.items():
            best_match_page_num2 = None
            best_match_ratio = 0

            for page_num2, page_text2 in text2.items():
                ratio = SequenceMatcher(None, page_text1, page_text2).ratio()

                if ratio > best_match_ratio:
                    best_match_ratio = ratio
                    best_match_page_num2 = page_num2

            # If the similarity is below the threshold, mark as None
            if best_match_ratio < self.page_similarity_threshold:
                self.aligned_pages.append((page_num1, None, best_match_ratio))
            else:
                self.aligned_pages.append((page_num1, best_match_page_num2, best_match_ratio))

        # Create a set to keep track of the pages that have been matched in the first pass
        matched_pages = set(page_num2 for _, page_num2, _ in self.aligned_pages if page_num2 is not None)

        # Second pass to align remaining pages in text2 to unmatched pages in text1
        for page_num2, page_text2 in text2.items():
            # Skip pages that have already been matched in the first pass
            if page_num2 in matched_pages:
                continue

            best_match_page_num1 = None
            best_match_ratio = 0

            for page_num1, page_text1 in text1.items():
                # You can use SequenceMatcher or fuzz.ratio here as per your preference
                ratio = SequenceMatcher(None, page_text1, page_text2).ratio()

                if ratio > best_match_ratio:
                    best_match_ratio = ratio
                    best_match_page_num1 = page_num1

            # If the similarity is below the threshold, mark as None
            if best_match_ratio < self.page_similarity_threshold:
                self.aligned_pages.append((None, page_num2, best_match_ratio))  # Mark as added page
            else:
                self.aligned_pages.append((best_match_page_num1, page_num2, best_match_ratio))

        # Identify pages in pages2 that don't have a match in pages1
        unmatched_pages2 = set(range(len(text2.items()))) - set(page_num2 for _, page_num2, _ in self.aligned_pages)
    
        # Append these unmatched pages to the end of aligned_pages
        self.aligned_pages += [(None, page_num2, 0) for page_num2 in unmatched_pages2 if page_num2 != 0]


    def comparePdfs(self):
        # Page variables
        self.removed_pages = []
        self.added_pages = []
        self.compared_pages = []
        self.page_changes = {}
        self.rejected_page_changes = {}

        # Text variables
        text1 = self.all_text['old']
        text2 = self.all_text['new']
        lines_added = []

        # Find differences between pages
        for page, text in text1.items():
            self.rejected_page_changes[page] = []
            
            pdf2pg = self.aligned_pages[page-1][1]
            # Record removed pages
            if pdf2pg == None:
                self.removed_pages.append(page)
                continue
            else:
                self.compared_pages.append(tuple((page,pdf2pg)))

            # Compare the PDFs!
            d = Differ() # From difflib
            diff = d.compare(text.splitlines(keepends=True), text2[pdf2pg].splitlines(keepends=True))
            text_comparison = ''.join(diff)
            changed_lines = [line for line in text_comparison.splitlines(keepends=True) if line.startswith('+ ') or line.startswith('- ')]
            changes = self.removeNoise(changed_lines)

            # Check for very similar lines - could be an OCR misread
            for added_change in changes:
                if added_change[:2] == "+ ":
                    similarity_ratio = 0
                    for removed_change in changes:
                        if removed_change[:2] == "- ":
                            if self.text_comparison_accuracy: similarity_ratio = SequenceMatcher(None, added_change[2:], removed_change[2:]).ratio() # SequenceMatcher from difflib
                            else: similarity_ratio = SequenceMatcher(None, added_change[2:], removed_change[2:]).quick_ratio() # SequenceMatcher from difflib

                        # Check if the similarity ratio is above the threshold
                        if similarity_ratio >= self.text_similarity_threshold:
                            self.rejected_page_changes[page] += added_change, removed_change, f"^^^ Similarity ratio: {similarity_ratio}"
                            break
            for item in self.rejected_page_changes[page]:
                try: changes.remove(item)
                except ValueError: continue
                            
            if len(changes) == 0: self.page_changes[page] = ["No differences found."]
            else: self.page_changes[page] = changes

            # Update current page for progress bar
            self.current_page += 1

        # Record added pages
        for item in self.aligned_pages:
            if item[0] == None: self.added_pages.append(item[1])

        # Clean up the rejected page changes variable
        remove_blank_changes = []
        for page, changes in self.rejected_page_changes.items():
            if len(changes) == 0: remove_blank_changes.append(page)
        for page in remove_blank_changes:
            del self.rejected_page_changes[page]


    def removeNoise(self, changed_lines):
        noise_reduced = []
        noise_test = ""
        for item in changed_lines:
            # Assume any blank line is noise
            if item == "+ \n" or item == "- \n": continue
            # Assume any text that is equal bar first 4 digits (e.g: "+ e ") is an OCR misread bullet point
            elif item[4:] == noise_test[2:]:
                noise_reduced.pop()
                continue
            elif item[2:] == noise_test[4:]:
                noise_reduced.pop()
                continue
            # Remove any new line characters
            elif item.endswith("\n"): noise_reduced_txt = item.strip("\n")
            else: noise_reduced_txt = item
            noise_test = item
            noise_reduced.append(noise_reduced_txt)
        return noise_reduced

   
    def documentDiffs(self):
        duplicate_page_match = []
        added_check_recommendation = []
        removed_check_recommendation = []
        with OpenFile(self.output_path) as f:
            # Document files being compared
            f.write(f"Files under comparison:\nOld file: {self.pdf_file_paths['old']}\nNew file: {self.pdf_file_paths['new']}")
            f.write("\n\n------------------------------------------------------------\n\n")
            
            # Document page alignment info in table format
            f.write("Page alignment information:\n|  Old\t|  New\t|\n")
            for item in self.aligned_pages:
                f.write(f"|{item[0]}\t|{item[1]}\t|")
                if item[0] == None:
                    f.write(f" <-- New document page {item[1]} added  \t\tBest page similarity ratio: {round(item[2],2)}")
                    added_check_recommendation.append(item[1])
                elif item[1] == None:
                    f.write(f" <-- Old document page {item[0]} removed\t\tBest page similarity ratio: {round(item[2],2)}")
                    removed_check_recommendation.append(item[0])
                if item[1] != None: duplicate_page_match.append(item[1])
                f.write("\n")
            if len(duplicate_page_match) != len(set(duplicate_page_match)):
                f.write("\nA page in the old document was matched to more than one page in the new document.\nYou may need to increase the page similarity threshold in settings.\n")
            f.write("\n\n------------------------------------------------------------\n\n")

            # Recommend added and removed pages to review
            if len(added_check_recommendation) != 0:
                f.write("The following pages were added to the new document: \n")
                for item in added_check_recommendation:
                    if added_check_recommendation.index(item) == 0:
                        f.write(f"Page {item}")
                    else: f.write(f", {item}")
            else: f.write("There are no added pages to review in the new document.")
            f.write("\n\n")

            if len(removed_check_recommendation) != 0:
                f.write("The following pages were removed from the old document: \n")
                for item in removed_check_recommendation:
                    if removed_check_recommendation.index(item) == 0:
                        f.write(f"Page {item}")
                    else: f.write(f", {item}")
            else: f.write("There are no removed pages to review in the old document.")
            f.write("\n\n------------------------------------------------------------\n\n")

            # Document changes
            f.write(f"Compared page content:\nList of compared pages (old,new): {self.compared_pages}\n")
            for page, changes in self.page_changes.items():
                f.write(f"Old document page {page} to new document page {self.aligned_pages[page-1][1]}:\n")
                for change in changes:
                    f.write(f"{change}\n")
                f.write("\n\n")
            f.write("\n\n------------------------------------------------------------\n\n")

            # Document rejections just in case
            if len(self.rejected_page_changes) == 0: f.write(f"There were no rejected changes (all text similarity was below the threshold {self.text_similarity_threshold}).")
            else:
                f.write(f"Rejected changes (text similarity above the threshold {self.text_similarity_threshold}) FIO:\n")
                for page, changes in self.rejected_page_changes.items():
                    f.write(f"Old document page {page} to new document page {self.aligned_pages[page-1][1]}:\n")
                    for change in changes:
                        f.write(f"{change}\n")
                    f.write("\n\n")
            f.write("\n\n------------------------------------------------------------\n\n")

            # Document settings used
            settings_text = f"""Settings used:
Page similarity threshold (ratio 0 to 1) = {self.page_similarity_threshold}\t<-- If the page is more similar than this ratio it will assume it's the same page, otherwise it's an added or removed page.
    
Text similarity threshold (ratio 0 to 1) = {self.text_similarity_threshold}\t<-- If the text is more similar than this ratio it will assume it's misread the text, otherwise it's a valid change to the documents content.
    
Text comparison accuracy (Boolean) = {self.text_comparison_accuracy}\t<-- False = Fast, True = Slower but more accurate
    
Cropped area (LH width, LH height, RH width, RH height: {self.crop_area}  <-- The pixels used to define the size of the page to scan for text, the top left corner is (0,0).

"""
            f.write(settings_text)

        # Check if any errors occured during documenting the output
        if check_consecutive_errors(max_attempts=1, look_for=f"An error occured while handling the file:\n{self.output_path}"): return False
        else: return True





class OpenFile():
    def __init__(self, output_path, config=False):
        if config: self.output_path = "./config.ini"
        else: self.output_path = output_path

    def __enter__(self):
        # Open the file in write mode first to remove any prior content, then open in append
        self.f = open(self.output_path,'w')
        self.f.close()
        self.f = open(self.output_path,'a')
        return self.f

    def __exit__(self, *args):
        self.f.close()
        if any(args):
            # An exception occurred
            exc_type, exc_value, traceback_str = args
            formatted_traceback = traceback.format_tb(traceback_str)[0]
            log_exc(f"An error occured while handling the file:\n{self.output_path}")
            messagebox.showinfo(title='File Handling Error Occured',message=f"An error occured while handling the {self.output_path} file.\n\nError type: {exc_type}\nError value: {exc_value}")





# Global error logging functions
def log_exc(*message, level=logging.ERROR, exc_info=None):
    """
    Log a message to the debug file.
    Parameters:
    - message (str, optional): The message to be logged or the default from sys
    - level (int, optional): 10=DEBUG, 20=INFO, 30=WARNING, 40=ERROR, 50=CRITICAL
    - exc_info (bool, optional): Include exception information in the log entry?
    """
    logging.basicConfig(filename='debug.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # If no message is provided, generate a default error message with exception information
    if not message:
        exception_info = sys.exc_info()
        message = f"An error occurred: {exception_info[0]} - {exception_info[1]}"
    elif len(message) == 1:
        message = message[0]

    # If no "exc_info" boolean provided, use default values based on error level
    if exc_info == None:
        if level > 25: exc_info = True
        else: exc_info = False

    try: logging.log(level, message, exc_info=exc_info)
    finally: logging.shutdown()


def check_consecutive_errors(log_file='debug.log', max_attempts=3, look_for="INFO"):
    consecutive_errors = 0

    with open(log_file, 'r') as file:
        # Read the last x lines from the end of the file
        last_lines = file.readlines()[-max_attempts:]

    for line in last_lines:
        if look_for in line:
            consecutive_errors += 1
            if consecutive_errors >= max_attempts:
                return True
    return False

    
GenerateUI()
