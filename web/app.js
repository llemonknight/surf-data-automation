document.addEventListener('DOMContentLoaded', () => {
    const reportForm = document.getElementById('surf-report');
    const submitBtn = document.getElementById('submit-btn');

    // 模擬從 API 載入數據 (未來可對接到 GitHub Actions 產出的 JSON 或直接對接 API)
    fakeLoadData();

    reportForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const spot = document.getElementById('spot').value;
        const rating = document.querySelector('input[name="rating"]:checked').value;
        const comments = document.getElementById('comments').value;

        // UI 狀態更新
        submitBtn.disabled = true;
        submitBtn.innerText = '傳送中...';

        const payload = {
            timestamp: new Date().toISOString(),
            spot: spot,
            rating: rating,
            comments: comments
        };

        console.log('Sending report:', payload);

        // 這裡未來需要對接到 Google Apps Script Web App
        // 為了解決跨網域寫入 Sheets 的問題，最好的做法是在 Google Sheet 寫一小段 Script 作為 Proxy

        try {
            // 這裡先用模擬延遲代表送出
            await new Promise(resolve => setTimeout(resolve, 1500));

            alert('✅ 回報成功！感謝你的分享。');
            reportForm.reset();
        } catch (error) {
            console.error('Error:', error);
            alert('❌ 發生錯誤，請稍後再試。');
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerText = '發送回報';
        }
    });
});

function fakeLoadData() {
    // 預填一些假數據展示效果
    document.getElementById('wave-height').innerText = '0.9m';
    document.getElementById('wave-period').innerText = '7s';
    document.getElementById('wind-speed').innerText = '4m/s';
    document.getElementById('sea-level').innerText = '0.2m';
    document.getElementById('last-update').innerText = new Date().toLocaleTimeString();
}
