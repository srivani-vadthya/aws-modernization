# aws-modernization

# start up Backend

cd \aws-modernization\apps\api
    python -m venv .venv
    .\.venv\Scripts\Activate
    pip install -r requirements.txt
    uvicorn app.main:app --reload --port 8000
 

# start up Frontend

cd \aws-modernization\apps\web
    npm install
    npm run dev