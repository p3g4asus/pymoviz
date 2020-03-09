# p4a clean_builds && p4a clean_dists
cd /home/matteo/python-for-android/pymoviz
cp main/main.main.py src/main.py
p4a apk --private /home/matteo/python-for-android/pymoviz/src --package=org.kivymfz.pymoviz --name "PyMoviz" --version 1.0 --bootstrap=sdl2 --requirements=libffi,python3,python-osc,kivy,setuptools,kivymd,aiosqlite,able --debug --permission INTERNET --permission WRITE_EXTERNAL_STORAGE --permission READ_EXTERNAL_STORAGE --permission FOREGROUND_SERVICE --permission ACCESS_COARSE_LOCATION --dist-name pymoviz_apk --service=DeviceManagerService:./service/device_manager_service.py

# # cd /home/matteo/.local/share/python-for-android/dists/pymoviz_apk && /home/matteo/.loal/share/python-for-android/dists/pymoviz_test_apk/gradlew assembleDebug
