# Upload progress update — 2026.10.20

මෙය ඔයා දුන්න video-setup-fixed (2).zip එකට දාන update එකක් පමණයි.

## දාන්න

ZIP එකේ scripts/ folder එකේ files තුනම දැනට තියෙන GitHub video repository එකේ scripts/ folder එකට copy/replace කර commit/push කරන්න. clixarena_upload_metrics.py අලුත් file එකත් අනිවාර්යයෙන් ඇතුළත් කරන්න. පරණ project එක delete කරන්න එපා. UI/API redeploy හෝ අලුත් secrets අවශ්‍ය නැහැ. දැනට ක්‍රියාත්මක run එකක code මාරු නොවේ; අලුත් run එකේ logs ලැබෙයි.

## Logs

Streamtape, StreamHG සහ Abyss uploads වල:

- ආරම්භයේ MP4 size එක.
- දිගු upload එකක තත්පර 10කට ආසන්නව progress %, sent MiB, average MiB/s, elapsed සහ estimated remaining time.
- Curl request එක අවසන් වූ පසු sent MiB, average MiB/s, transfer/request time සහ connection/setup time.
- Metadata/filename verification සහ mapping save සඳහා වෙන වෙනම elapsed time.
- Streamtape checksum preparation සහ upload-server lookup සඳහාද වෙනම කාලය.

උදාහරණ:

    StreamHG upload 45% | sent 450.00 MiB | average 5.00 MiB/s | elapsed 90s | estimated remaining 110s
    StreamHG transfer finished: sent 1000.00 MiB | average 5.00 MiB/s | transfer/request 200.0s | connection/setup 0.5s
    StreamHG mapping save finished: 1.2s
    StreamHG metadata verification finished: 25.4s

මේවා පැහැදිලි කිරීමට යොදාගත් අංක පමණයි; ඔයාගේ සැබෑ upload වේගය නෙවෙයි. MiB = 1024x1024 bytes. Sent count එකට multipart overhead ටිකත් ඇතුළත් විය හැකියි. Live values meter rounding නිසා approximate; අවසාන summary curl metrics භාවිත කරයි. කෙටි upload එකක් තත්පර 10ට පෙර ඉවර වුණොත් final summary එක පමණක් ලැබිය හැකියි. Transfer/request time එකට server response එක ලැබෙන තෙක් ගතවන කාලයත් ඇතුළත්ය; පසුව metadata verification වෙනම මනී.

API keys, upload URLs, video IDs, filenames සහ raw API/curl responses telemetry logs වල පෙන්වන්නේ නැහැ. Curl stderr privately parse කර numeric progress පමණක් පෙන්වයි. TLS validation, host upload order, mapping encryption, runner mode සහ upload retry policy වෙනස් කරලා නැහැ. Failed/uncertain upload ස්වයංක්‍රීයව retry කරන්නේ නැහැ.

මෙය speed වැඩි කරන update එකක් නොවෙයි. Upload transfer එකද, පසුව verification එකද slow කියලා logs වලින් වෙන් කර බලන්න හදපු update එකයි. සත්‍ය host upload එකක් හෝ GitHub run එකක් ආරම්භ කර නැහැ.
