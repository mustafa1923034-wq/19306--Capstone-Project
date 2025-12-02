# test_accuracy.py
import os
import sys
from stable_baselines3 import PPO

# إضافة المسار علشان يشوف الملفات
sys.path.append(os.path.dirname(__file__))

from sumo_env import SumoTrafficEnv
from accuracy_calculator import calculate_system_accuracy

def main():
    print("🔧 تهيئة النظام...")
    
    # 1. شغل البيئة
    env = SumoTrafficEnv()
    
    # 2. اتأكد إن الموديل موجود
    model_path = "models/ppo_sumo_final.zip"
    if not os.path.exists(model_path):
        print(f"❌ مفيش موديل في {model_path}")
        print("🔍 جاري البحث عن أي موديل...")
        
        models_dir = "models/"
        if os.path.exists(models_dir):
            files = os.listdir(models_dir)
            if files:
                model_path = os.path.join(models_dir, files[0])
                print(f"✅ تم إيجاد: {model_path}")
            else:
                print("❌ مفيش موديلات في folder models/")
                return
        else:
            print("❌ مفيش folder models/")
            return
    
    # 3. حمل الموديل
    print(f"📂 جاري تحميل الموديل: {model_path}")
    model = PPO.load(model_path, env=env)
    print("✅ تم تحميل الموديل بنجاح")
    
    # 4. احسب الدقة
    accuracy = calculate_system_accuracy(env, model, num_tests=5, steps_per_test=30)
    
    # 5. النتيجة النهائية
    print(f"\n🎊 النتيجة النهائية: الدقة = {accuracy:.1f}%")
    
    # 6. اقفل البيئة
    env.close()

if __name__ == "__main__":
    main()
    