# p4a clean_builds && p4a clean_dists
cd /home/matteo/python-for-android/pymoviz
cp main/main.test.py src/main.py
p4a apk --private /home/matteo/python-for-android/pymoviz/src --package=org.kivymfz.pymoviz.test --name "PyMovizTest" --version 1.0 --bootstrap=sdl2 --requirements=libffi,python3,python-osc,kivy,setuptools,kivymd,aiosqlite,able,airspeed --debug --permission INTERNET --permission WRITE_EXTERNAL_STORAGE --permission READ_EXTERNAL_STORAGE --permission FOREGROUND_SERVICE --permission ACCESS_FINE_LOCATION --permission BLUETOOTH --permission BLUETOOTH_ADMIN --dist-name pymoviz_test_apk --service=BluetoothService:./test/service/bluetooth_service.py

# cd /home/matteo/.local/share/python-for-android/dists/pymoviz_test_apk && /home/matteo/.local/share/python-for-android/dists/pymoviz_test_apk/gradlew assembleDebug
