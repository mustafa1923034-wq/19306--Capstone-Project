from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ---------------------------
# قيم هتتحدث من السيستم الحقيقي
# ---------------------------
data = {
    "density": [0, 0, 0, 0],
    "beacon": False,
    "time_response": 0.0,
    "priority_lane": None,
    "next_green": [30, 30, 30, 30]
}

# ---------------------------
# استلام تحديث من النظام الأساسي
# ---------------------------
@app.route("/update", methods=["POST"])
def update():
    payload = request.json

    data["density"] = payload.get("density", data["density"])
    data["beacon"] = payload.get("beacon", data["beacon"])
    data["time_response"] = payload.get("time_response", data["time_response"])
    data["next_green"] = payload.get("next_green", data["next_green"])

    return jsonify({"status": "updated"})


# ---------------------------
# الداشبورد يطلب البيانات
# ---------------------------
@app.route("/get")
def get_data():
    return jsonify(data)


# ---------------------------
# الداشبورد يرسل lane المختار للطوارئ
# ---------------------------
@app.route("/set_lane", methods=["POST"])
def set_lane():
    lane = request.json.get("lane", None)
    data["priority_lane"] = lane
    return jsonify({"status": "priority updated"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
