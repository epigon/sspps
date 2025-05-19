Install VirtualEnv name: venv
1.  VSCode terminal (or Command Prompt)
2.  pip install virtualenv
3.  virtualenv virtualDirName (python -m venv virtualDirName)
4.  virtualDirName\Scripts\activate

Install dependencies
-   Command Prompt or PowerShell (Run as Administrator)
- 	pip install -r requirements.txt

Copy app/cred.py directly to server, content should look like this
server = '###'
user = '###'
pwd = '###'
database = '###'
secret = '###'

To run in server, install WFastCGI
-   wfastcgi.py file needs to be in root folder
-   activate venv venv\Scripts\activate
-   cd venv\Scripts
-   run wfastcgi-enable.exe
-   Go to IIS SERVER – FastCGI Settings
    -   EnvironmentVariables
        -   Add PYTHONPATH, Value: E:\www\sspps-dev
        -   Add WSGI_HANDLER, Value: run.app

