/**
 * Cloudflare Worker for PDF Order Parsing & Mini App Integration
 */

export default {
  async fetch(request, env, ctx) {
    // Handle CORS
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
        },
      });
    }

    const url = new URL(request.url);

    // Endpoint for API parsing if needed
    if (url.pathname === "/api/parse-pdf" && request.method === "POST") {
      try {
        const body = await request.json();
        const text = body.text || "";
        const products = parseProductsFromText(text);
        return new Response(JSON.stringify({ success: true, count: products.length, products }), {
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
          },
        });
      } catch (err) {
        return new Response(JSON.stringify({ success: false, error: err.message }), {
          status: 400,
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
        });
      }
    }

    // Default HTML UI Response
    return new Response(getHTMLPage(), {
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
      },
    });
  },
};

function parseProductsFromText(text) {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const products = [];
  const rowPattern = /^(?:\|\s*)?(\d+)\s+(.+?)\s*\|?\s*([\d\s\.,]+)\s*\|?\s*(\d+)\s*\|?\s*([а-яА-Яa-zA-Z]+|\b)\s*\|?\s*([\d\s\.,]+)/;

  let currentItem = null;

  for (let line of lines) {
    const cleanLine = line.replace(/^\|/, '').trim();
    const match = cleanLine.match(rowPattern);

    if (match) {
      if (currentItem) products.push(currentItem);
      
      const costPrice = parseFloat(match[3].replace(/\s/g, '').replace(',', '.'));
      const totalAmount = parseFloat(match[6].replace(/\s/g, '').replace(',', '.'));

      currentItem = {
        id: parseInt(match[1], 10),
        title: match[2].trim(),
        cost_price: costPrice, // Цена из накладной фиксируется как себестоимость
        quantity: parseInt(match[4], 10),
        unit: match[5] || 'шт',
        total_sum: totalAmount
      };
    } else if (currentItem) {
      if (!line.includes('Итого') && !line.includes('ЗАКАЗ №') && !line.includes('Заказчик') && !line.includes('Наименование')) {
        if (!line.startsWith('|')) {
          currentItem.title += ' ' + line.trim();
        }
      }
    }
  }

  if (currentItem) products.push(currentItem);
  return products;
}

function getHTMLPage() {
  return `<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Импорт товаров из PDF (Себестоимость)</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
  <style>
    :root {
      --bg-color: #121820;
      --card-bg: #1e2630;
      --accent: #00b4d8;
      --accent-hover: #0096c7;
      --text-main: #f0f4f8;
      --text-sub: #94a3b8;
      --border-color: #2e3846;
      --success: #06d6a0;
      --error: #ef476f;
    }
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg-color);
      color: var(--text-main);
      margin: 0;
      padding: 20px;
    }
    .container { max-width: 900px; margin: 0 auto; }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 20px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    h2, h3 { margin-top: 0; }
    .upload-zone {
      display: flex;
      flex-direction: column;
      gap: 15px;
      align-items: flex-start;
    }
    input[type="file"] {
      background: #161c24;
      padding: 12px;
      border-radius: 8px;
      border: 1px solid var(--border-color);
      color: var(--text-main);
      width: 100%;
    }
    button {
      background: var(--accent);
      color: #fff;
      border: none;
      padding: 12px 24px;
      border-radius: 8px;
      font-weight: bold;
      font-size: 16px;
      cursor: pointer;
      transition: background 0.2s;
    }
    button:hover { background: var(--accent-hover); }
    .status { margin-top: 10px; font-weight: 600; }
    table { width: 100%; border-collapse: collapse; margin-top: 15px; }
    th, td {
      border: 1px solid var(--border-color);
      padding: 10px 14px;
      text-align: left;
    }
    th { background: #161c24; color: var(--text-sub); font-weight: 600; }
    tr:nth-child(even) { background: rgba(255,255,255,0.02); }
    .badge {
      background: #00b4d822;
      color: var(--accent);
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 13px;
    }
  </style>
</head>
<body>
  <div class="container">
    <h2>Импорт PDF накладных в Магазин</h2>
    
    <div class="card">
      <div class="upload-zone">
        <label><b>Выберите PDF файл накладной:</b></label>
        <input type="file" id="pdfFile" accept="application/pdf">
        <button onclick="processPdf()">Распознать товары</button>
      </div>
      <div id="status" class="status"></div>
    </div>

    <div class="card">
      <h3>Распознанные товары (<span id="count">0</span>)</h3>
      <div style="overflow-x: auto;">
        <table id="productsTable">
          <thead>
            <tr>
              <th>№</th>
              <th>Наименование</th>
              <th>Кол-во</th>
              <th>Ед.</th>
              <th>Себестоимость (cost_price)</th>
              <th>Сумма</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    // ОВЕРРАЙД WORKER_SRC ДЛЯ УСТРАНЕНИЯ ОШИБКИ "No GlobalWorkerOptions.workerSrc specified"
    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

    async function processPdf() {
      const fileInput = document.getElementById('pdfFile');
      const statusDiv = document.getElementById('status');
      const tbody = document.querySelector('#productsTable tbody');
      const countSpan = document.getElementById('count');

      tbody.innerHTML = '';
      countSpan.textContent = '0';

      if (!fileInput.files.length) {
        statusDiv.style.color = 'var(--error)';
        statusDiv.textContent = 'Пожалуйста, выберите файл PDF!';
        return;
      }

      statusDiv.style.color = '#ffd166';
      statusDiv.textContent = 'Чтение и анализ страниц PDF...';

      try {
        const file = fileInput.files[0];
        const arrayBuffer = await file.arrayBuffer();
        
        const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
        let fullText = '';

        for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
          const page = await pdf.getPage(pageNum);
          const textContent = await page.getTextContent();
          
          let lastY = null;
          let pageText = '';
          for (const item of textContent.items) {
            if (lastY !== null && Math.abs(item.transform[5] - lastY) > 5) {
              pageText += '\n';
            }
            pageText += item.str + ' ';
            lastY = item.transform[5];
          }
          fullText += pageText + '\n';
        }

        const products = parseProductsFromText(fullText);

        if (products.length === 0) {
          statusDiv.style.color = 'var(--error)';
          statusDiv.textContent = 'Товары не найдены. Проверьте правильность выбранного PDF.';
          return;
        }

        statusDiv.style.color = 'var(--success)';
        statusDiv.textContent = \`Успешно обработано! Найдено товаров: \${products.length}\`;
        countSpan.textContent = products.length;

        products.forEach(item => {
          const tr = document.createElement('tr');
          tr.innerHTML = \`
            <td>\${item.id}</td>
            <td>\${item.title}</td>
            <td>\${item.quantity}</td>
            <td>\${item.unit}</td>
            <td><b>\${item.cost_price.toFixed(2)} ₽</b></td>
            <td>\${item.total_sum.toFixed(2)} ₽</td>
          \`;
          tbody.appendChild(tr);
        });

      } catch (err) {
        console.error(err);
        statusDiv.style.color = 'var(--error)';
        statusDiv.textContent = 'Ошибка при парсинге PDF: ' + err.message;
      }
    }

    function parseProductsFromText(text) {
      const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
      const products = [];
      const rowPattern = /^(?:\|\s*)?(\d+)\s+(.+?)\s*\|?\s*([\d\s\.,]+)\s*\|?\s*(\d+)\s*\|?\s*([а-яА-Яa-zA-Z]+|\b)\s*\|?\s*([\d\s\.,]+)/;

      let currentItem = null;

      for (let line of lines) {
        const cleanLine = line.replace(/^\|/, '').trim();
        const match = cleanLine.match(rowPattern);

        if (match) {
          if (currentItem) products.push(currentItem);
          
          const costPrice = parseFloat(match[3].replace(/\s/g, '').replace(',', '.'));
          const totalAmount = parseFloat(match[6].replace(/\s/g, '').replace(',', '.'));

          currentItem = {
            id: parseInt(match[1], 10),
            title: match[2].trim(),
            cost_price: costPrice,
            quantity: parseInt(match[4], 10),
            unit: match[5] || 'шт',
            total_sum: totalAmount
          };
        } else if (currentItem) {
          if (!line.includes('Итого') && !line.includes('ЗАКАЗ №') && !line.includes('Заказчик') && !line.includes('Наименование')) {
            if (!line.startsWith('|')) {
              currentItem.title += ' ' + line.trim();
            }
          }
        }
      }

      if (currentItem) products.push(currentItem);
      return products;
    }
  </script>
</body>
</html>`;
}
