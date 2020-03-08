# p4a clean_builds && p4a clean_dists
cp main/main.tst.py src/main.py
p4a apk --private /home/matteo/python-for-android/pymoviz/src --package=org.kivymfz.pymoviz.test --name "PyMoviz" --version 1.0 --bootstrap=sdl2 --requirements=libffi,python3,python-osc,kivy,setuptools,kivymd,aiosqlite,able --debug --permission INTERNET --permission WRITE_EXTERNAL_STORAGE --permission READ_EXTERNAL_STORAGE --permission FOREGROUND_SERVICE --permission ACCESS_COARSE_LOCATION --dist-name pymoviz_test_apk --service=BluetoothService:./service/bluetooth_service.py

# cd /home/matteo/.local/share/python-for-android/dists/playlistmanager_apk && /home/matteo/.local/share/python-for-android/dists/playlistmanager_apk/gradlew assembleDebug
