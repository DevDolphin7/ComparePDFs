For help, see "Help.txt"! Or launch the app, click "Settings" and then "Help"


For any questions, issues, or feedback, feel free to send the "debug.log" file and get in touch on:
Email: DevDolphin7@outlook.com
GitHub: https://github.com/DevDolphin7/ComparePDFs


The code requires the following packages to run, these are included in the install file:
- pytersseract Version 0.3.10
- SpaCy Version 3.7.2
	SpaCy using `en_core_web_sm` Version `3.7.1` (requires spaCy `>=3.7.2,<3.8.0`)
- pdf2image Version 1.16.3
- It also utilises difflib which can be installed through pip.


CM Content Extractor - Original concept. Used Deepdiff, had GUI.
ComparePDFsv1 - Broader scope, no GUI. Using Deepdiff, struggled with encoding errors.
ComparePDFsv2 - Started using OCR! Compare function working.
ComparePDFsv3 - OCR with a GUI. First compile attempt.
ComparePDFsv4 - OCR then Deepdiff result.
ComparePDFsv5 - Moving away from Deepdiff to difflib. Page alignmenet based on content & polish the app
ComparePDFsv6 - Reconstruct text into sentances, then compare the sentences
