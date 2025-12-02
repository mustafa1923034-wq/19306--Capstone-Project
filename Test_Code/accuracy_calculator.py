# accuracy_calculator.py
import numpy as np

def calculate_system_accuracy(env, model, num_tests=10, steps_per_test=50):
    """
    احسب دقة النظام بالمقارنة مع النظام العادي
    """
    print("🚀 بدء حساب دقة النظام...")
    
    # 1. اختبار النظام العادي
    print("🔹 جاري اختبار النظام العادي...")
    normal_scores = []
    
    for test in range(num_tests):
        obs, _ = env.reset()
        total_reward = 0
        
        for step in range(steps_per_test):
            action = np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32)  # 30 ثانية للكل
            obs, reward, done, _, _ = env.step(action)
            total_reward += reward
            if done: break
        
        normal_scores.append(total_reward)
        print(f"   اختبار {test+1}: {total_reward:.2f}")
    
    # 2. اختبار النظام الذكي
    print("🔹 جاري اختبار النظام الذكي...")
    smart_scores = []
    
    for test in range(num_tests):
        obs, _ = env.reset()
        total_reward = 0
        
        for step in range(steps_per_test):
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, _, _ = env.step(action)
            total_reward += reward
            if done: break
        
        smart_scores.append(total_reward)
        print(f"   اختبار {test+1}: {total_reward:.2f}")
    
    # 3. حساب النتائج
    avg_normal = np.mean(normal_scores)
    avg_smart = np.mean(smart_scores)
    
    if avg_normal == 0:
        accuracy = 100.0
    else:
        accuracy = (avg_smart / avg_normal) * 100
    
    print("\n" + "="*50)
    print("📊 نتائج اختبار الدقة")
    print("="*50)
    print(f"🔸 النظام العادي: {avg_normal:.2f}")
    print(f"🔸 النظام الذكي:  {avg_smart:.2f}")
    print(f"🎯 الدقة: {accuracy:.1f}%")
    
    if accuracy >= 150:
        print("📈 التقييم: ممتاز 🎉")
    elif accuracy >= 120:
        print("📈 التقييم: جيد جداً ✅")
    elif accuracy >= 100:
        print("📈 التقييم: جيد ⭐")
    elif accuracy >= 80:
        print("📈 التقييم: مقبول ⚠️")
    else:
        print("📈 التقييم: يحتاج تطوير 🚧")
    
    print("="*50)
    
    return accuracy