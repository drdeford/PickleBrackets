from flask import Flask, render_template, request, redirect, url_for, session
#from flask_session import Session
import csv
import json
import logging
import requests
import math

app = Flask(__name__)
#SESSION_TYPE = 'redis'
#app.config.from_object(__name__)
#Session(app)
app.secret_key = "1769"

#"""
@app.before_request
def log_the_request():
    logger.info(request.remote_addr)
    logger.info(request)
#"""    
    
@app.route("/")
def index():

    return render_template("index.html")


@app.route("/submitRR", methods=["GET", "POST"])
def submitRR():
    if request.method == "GET":
        return redirect(url_for('index'))
    elif request.method == "POST":
    
        userdata = dict(request.form)

        n = int(userdata['numplay'])
        
        session['numplays'] = n
        
        names = [str(x) for x in range(1,n+1)]
        
        rlist = []
        
        for entry in names: 
            rlist.append({"id":int(entry),"label":f"p{int(entry)}"})
        
        
        if n < 4 or n > 24:
            return render_template("RRwrong.html")
            
        #print(userdata)
        
        
        
        #if userdata['binnames'] == 'names_y':
        if 'binnames' in list(userdata.keys()):
            return render_template("gather_names.html", numplays=rlist)
        
        
        

        #url = f"http://math.wsu.edu/faculty/ddeford/PB_Brackets/pb{n}.json"
        #r = requests.get(url)
        #wdict = r.json()
        
        with open(f'{app.root_path}/static/pb{n}.json', 'r') as f:
            wdict = json.load(f)
        
        courts = math.floor(n/4)
        byes = n%4

        rows = [['Court ' + str(x+1) for x in range(courts)]]
        if byes > 0: 
        	rows[0].append('Bye(s)')
        rows[0].insert(0,'Round')

        for i in range(len(wdict[str(n)])):
        	rows.append([])
        	row = wdict[str(n)][i]
        	for j in range(courts):
                #print(courts)
                #print(row)

        		rows[-1].append(names[row[j][0][0]] + '/' + names[row[j][0][1]] + " vs. " + names[row[j][1][0]] + '/' + names[row[j][1][1]])
                #print(rows)
        	if byes >0: 
        		rows[-1].append(names[row[-1][0]])
        		for k in range(1,byes):
        			rows[-1][-1] = rows[-1][-1] + " " + (names[row[-1][k]])

        	rows[-1].insert(0,str(i+1))
            
        return render_template("RR.html", plist=rows)
    
@app.route("/submitRR2", methods=["GET", "POST"])
def submitRR2():
    if request.method == "GET":
        return redirect(url_for('index'))
    elif request.method == "POST":
    
        #numplays = session.get("numplays")
    
        userdata = dict(request.form)

        n = session.get("numplays")
        #names = [str(x) for x in range(1,n+1)]
        
        names = [userdata[f"p{x+1}"] for x in range(n)]

        #url = f"http://math.wsu.edu/faculty/ddeford/PB_Brackets/pb{n}.json"
        #r = requests.get(url)
        #wdict = r.json()
        
        with open(f'{app.root_path}/static/pb{n}.json', 'r') as f:
            wdict = json.load(f)

        courts = math.floor(n/4)
        byes = n%4

        rows = [['Court ' + str(x+1) for x in range(courts)]]
        if byes > 0: 
        	rows[0].append('Bye(s)')
        rows[0].insert(0,'Round')

        for i in range(len(wdict[str(n)])):
        	rows.append([])
        	row = wdict[str(n)][i]
        	for j in range(courts):
                #print(courts)
                #print(row)

        		rows[-1].append(names[row[j][0][0]] + '/' + names[row[j][0][1]] + " vs. " + names[row[j][1][0]] + '/' + names[row[j][1][1]])
                #print(rows)
        	if byes >0: 
        		rows[-1].append(names[row[-1][0]])
        		for k in range(1,byes):
        			rows[-1][-1] = rows[-1][-1] + " " + (names[row[-1][k]])

        	rows[-1].insert(0,str(i+1))
            
        return render_template("RR.html", plist=rows)
                        
if __name__ == "__main__":
    from waitress import serve
    #logging.basicConfig(filename='app.log',level=logging.DEBUG)
    logger = logging.getLogger('waitress')
    logger.setLevel(logging.INFO)
    
    handler = logging.FileHandler('app2.log')
    logger.addHandler(handler)
    
    serve(app, host="0.0.0.0", port=8080)
    #app.run() #recomment for wsgi
