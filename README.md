# movie-clip-agent

在自己電腦上執行的 Discord agent。在指定頻道傳一張影視截圖，或打出一句台詞，它用 `claude -p`（必要時上網搜尋查證）找出這是哪一部電影、影集或動畫，記進 Excel、存截圖，再回覆上傳者與今天頻道裡已找到的作品數。

動機：網路上常看到令人感興趣的影視片段或台詞金句，卻不知道出自哪部作品。

- 需求：`docs/requirements.md`
- 架構與設計決定：`docs/architecture.md`
- Discord 設定步驟：`docs/discord-server-setup.md`、`docs/discord-bot-setup.md`

agent 開著才會運作。關掉就不處理，重新開啟也不會補處理關掉期間傳的訊息。

## 啟動

在專案資料夾（`C:\Users\88693\movie-clip-agent`）打開終端機，輸入：

```
uv run movie-agent
```

第一次執行 uv 會自動建立環境並安裝套件（Python 3.12）。看到這一行就表示連上了：

```
INFO movie_agent.bot: 已連線：movie-clip-agent#xxxx，只處理頻道 ...
```

關掉：在終端機按 `Ctrl + C`。

啟動前先準備好 `.env`（從 `.env.example` 複製）：`DISCORD_TOKEN`、`CHANNEL_ID`、`CLAUDE_MODEL`、`DATA_DIR`。缺哪一項，啟動時會直接告訴你。

## 使用者看到什麼

1. 在指定頻道傳截圖、打一句台詞，或兩個一起：該則訊息上出現 ⏳（收到、排隊中）。
2. 處理完：⏳ 消失，出現 ✅（失敗是 ❌），並有一則「回覆」，內容是片名、原文名稱、年份、類型、片段說明、角色、信心程度、判斷依據，以及**今天頻道裡已找到幾部作品**（整個頻道今天的合計，不分人）。
3. 找不到時也會回覆「沒有找到確定的作品」加原因，一樣建檔、存截圖，但不計入當日數量。
4. 不是影視畫面也會回覆、建檔、存截圖，辨識結果欄寫「不是影視畫面」，片段說明欄寫判定出來的東西。
5. 只傳影片：回覆請改傳截圖或打出台詞。不分析影片。
6. 少於 2 個字的文字（例如「嗯」）不理。
7. 失敗時回覆「查詢失敗，請再傳一次」，不建檔。

例如打「I'll be back」，回覆會像這樣：

```
@小明
找到了：《魔鬼終結者》（The Terminator，1984，電影）
片段：終結者在警察局被拒絕進入後說出「I'll be back」，隨後駕車衝進警局
角色：終結者 T-800
信心程度：中
判斷依據：此句為該片經典名句；但也出現在續集及其他作品，故信心中等
今天頻道裡已找到 1 部作品（整個頻道今天的合計）
（結果由 AI 判斷並上網查證，仍可能有誤）
```

## log：處理過程看得到、也有記錄

每一步都會顯示在終端機，同時寫進 `DATA_DIR/agent.log`（單檔上限 5 MB，保留 3 份舊檔）。同一則訊息的紀錄開頭有同一個編號 `[#456789]`：

```
INFO movie_agent.bot: [#456789] 收到：上傳者 小明（42），1 張圖片，文字 26 字：'Luke, I am your father.'
INFO movie_agent.bot: [#456789] 已排隊：處理中 0 則，等待中 1 則（含這一則）
INFO movie_agent.bot: [#456789] 開始處理（在佇列裡等了 0.0 秒）
INFO movie_agent.pipeline: [#456789] 下載完成：1 張，共 186 KB
INFO movie_agent.analyzer: [#456789] 呼叫 claude -p（第 1/2 次，模型 sonnet，1 張截圖，有文字）
INFO movie_agent.analyzer: [#456789] claude -p 完成：耗時 12.4 秒，2 輪，估算費用 $0.0181（牌價）
INFO movie_agent.pipeline: [#456789] 分析結果：找到 星際大戰五部曲：帝國大反擊（Star Wars: Episode V，1980，電影），信心 高
INFO movie_agent.pipeline: [#456789] 已存截圖：screenshots/2026-10-20 21-05-11 星際大戰五部曲_帝國大反擊.png
INFO movie_agent.pipeline: [#456789] 已寫入 Excel：1 列，當日已找到作品數 3
INFO movie_agent.bot: [#456789] 已回覆（212 字）
INFO movie_agent.bot: [#456789] 完成：處理 12.6 秒，從收到算起共 12.6 秒
```

「2 輪」表示 `claude -p` 有用 WebSearch 查證過。拒絕（只有影片、格式不支援、檔案太大、排隊已滿）、分析不合格、Excel 寫不進去等情況都是 `WARNING` 或 `ERROR`。不會記錄 `DISCORD_TOKEN`、`claude` 的完整輸出，上傳者的文字只留前 50 字。

## 資料放在哪

都在 `DATA_DIR` 底下：

```
DATA_DIR/
├─ movie_log.xlsx    紀錄檔。新的一列加在最後，不會覆蓋
├─ screenshots/      截圖，檔名 YYYY-MM-DD hh-mm-ss 作品名稱.jpg，同一秒撞名加 -2、-3
└─ agent.log         log 檔
```

Excel 欄位：日期時間、上傳者、查詢方式、查詢文字、辨識結果、作品名稱、原文名稱、年份、類型、片段說明、信心程度、當日已找到作品數、截圖存放位置。

**Excel 開著的時候 agent 寫不進去。** 終端機會印出 `[警告]` 並重試幾次，仍然不行就回覆「記錄檔現在寫不進去，這次沒有記錄」。不看資料時請把 Excel 關掉。

## 四段防護在哪裡

每一段都用這種註解包起來：

```
# ==== 防護 N：名稱　開始 ====
...
# ==== 防護 N 結束 ====
```

每一段前面都有一行「沒有防護時的預設寫法」，防護段落再覆蓋它。所以**把某一段整段註解掉，程式照樣能跑**，只是少了那一層防護。一開始四段全部開著。

| 防護 | 檔案 | 約在第幾行 | 做什麼 |
|---|---|---|---|
| 防護 1：`claude -p` 的檔案範圍隔離 | `src/movie_agent/analyzer.py` | 109 到 120 | 每則訊息建一個暫存資料夾，只放這一則的截圖；`claude -p` 只能讀那裡、只能用 Read 和 WebSearch，不能讀 `DATA_DIR`、不能執行指令或打開網頁 |
| 防護 2：上傳者文字只當資料 | `src/movie_agent/analyzer.py` | 133 到 139 | 上傳者打的台詞只放進 `<uploader_text>` 標籤並截短、去掉角括號，不接進指令 |
| 防護 3：檔名清洗 | `src/movie_agent/storage.py` | 49 到 54 | 片名當檔名前，去掉 `/`、`\`、`..`、冒號等，並確認路徑在截圖資料夾裡 |
| 防護 4：Excel 公式字元處理 | `src/movie_agent/ledger.py` | 84 到 87 | 以 `=`、`+`、`-`、`@` 開頭的文字（包含上傳者打的台詞），前面加單引號並標成文字格 |

行號是約數，改過程式後請重新查：

```
grep -nE "防護 [1-4]：.*開始|防護 [1-4] 結束" src/movie_agent/*.py
```

註解掉某一段之後，跑一次測試看看哪些項目會失敗，那就是這一段原本擋住的事情：

```
uv run pytest
```

## 測試

```
uv run pytest
```

自動測試不連 Discord、不呼叫真的 `claude`。涵蓋 JSON 驗證、訊息分類、檔名清洗與撞名、Excel 往下加與當日累計、公式字元、排隊、四段防護的行為，以及整個處理流程。

## 注意事項

- `.env` 不可以 commit，裡面有 bot token。`DATA_DIR` 裡的截圖、Excel、log 也不可以 commit。`.gitignore` 已經擋住 `.env`、`.env.*`（`.env.example` 除外）、`movie-data/`、`data/`、`screenshots/`、`*.xlsx`。
- `DATA_DIR` 建議放在專案資料夾之外（例如 `C:\Users\88693\movie-data`）。
- 每處理一則訊息就會呼叫一次 `claude -p`（不合格時最多再試一次），而且有搜尋時會跑好幾輪，用掉你自己 Claude 帳號的額度。**純文字也會觸發查詢**，所以這個頻道請當成專用查詢頻道，不要在裡面聊天。能在那個頻道打字的人，就是能花你額度的人。
- 找不到頻道、bot 缺權限，啟動時會在終端機警告。
- 啟動後連上了，但傳訊息完全沒反應：到 Developer Portal 的 Bot 頁，確認 **Message Content Intent** 是開著的。

## 資料夾結構

```
src/movie_agent/
├─ main.py        進入點：讀設定、啟動
├─ config.py      讀 .env、各種預設上限
├─ bot.py         Discord：收訊息、分類（截圖／影片／台詞）、加反應、回覆
├─ queueing.py    排隊：一次只處理一則
├─ pipeline.py    處理一則訊息的流程：下載、查詢、存截圖、建檔、組回覆
├─ logs.py        log 設定：終端機加 agent.log，每則訊息一個 [#編號]
├─ analyzer.py    呼叫 claude -p（防護 1、防護 2）
├─ schema.py      JSON 格式與驗證
├─ storage.py     存截圖、命名（防護 3）
├─ ledger.py      Excel 紀錄、當日累計（防護 4）
├─ replies.py     回覆文字
└─ models.py      共用的資料型別
tests/            自動測試
```
