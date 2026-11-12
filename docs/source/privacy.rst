Privacy policy
==============

Last updated: 12 November 2026.

BILBO is a self-hosted RNA-Seq analysis platform. Each installation is operated by its administrator, who controls its server and the research data stored there. This page describes how BILBO's Google Drive import works. For questions about a particular installation or removal of imported data, contact that installation's administrator.

Google Drive access
-------------------

When you choose **Import from Google Drive** in Sample Management, BILBO asks you to authorize your Google account. It requests the ``drive.file`` scope so you can choose files with Google Picker and BILBO can download those selected files. Opening the import dialog starts a new authorization flow. The import is optional; other BILBO functions do not require a Google account.

BILBO receives the names, identifiers, sizes and checksums of selected files. Its server downloads the selected FASTQ files directly from Google Drive and stores them with your samples. The files do not pass through your computer. BILBO does not use this integration to modify or delete your Google Drive files.

Storage and retention
---------------------

The installation stores the imported FASTQ files and sample/job records on its server for analysis. They remain there until removed according to the installation administrator's data retention practices. Google authorization credentials are encrypted in the installation's temporary Redis storage and expire after at most 72 hours, allowing an import in progress to finish. Job progress records can remain temporarily for up to seven days.

Access to imported data follows the BILBO installation's user authentication and administrator controls. The installation operator is responsible for securing its server and for handling requests to access or delete stored research data.

Contact and changes
-------------------

For questions about this project's Drive integration or this policy, `open an issue in the BILBO repository <https://github.com/Lucianov-TheFarmer/BILBO/issues>`_. For questions about data held on a specific BILBO server, contact that server's administrator.
