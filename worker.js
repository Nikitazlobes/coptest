import pdfParse from 'pdf-parse';

export default {
  async fetch(request, env, ctx) {
    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Content-Type': 'application/json'
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders });
    }

    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'Используйте метод POST' }), { status: 405, headers: corsHeaders });
    }

    try {
      const formData = await request.formData();
      const file = formData.get('file');

      if (!file) {
        return new Response(JSON.stringify({ error: 'Загрузите PDF файл под ключом "file"' }), { status: 400, headers: corsHeaders });
      }

      const buffer = Buffer.from(await file.arrayBuffer());
      const pdfData = await pdfParse(buffer);
      const text = pdfData.text || '';

      const products = parseOrderPdf(text);

      return new Response(JSON.stringify({
        success: true,
        total_items: products.length,
        products: products
      }), { status: 200, headers: corsHeaders });

    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), { status: 500, headers: corsHeaders });
    }
  }
};

function parseOrderPdf(text) {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const products = [];
  
  // Регулярное выражение для формата заказов/накладных (включая символы | и разделители)
  const rowPattern = /^(?:\|\s*)?(\d+)\s+(.+?)\s*\|\s*([\d\s\.,]+)\s*\|\s*(\d+)\s*\|\s*([а-яА-Яa-zA-Z]+|\b)\s*\|\s*([\d\s\.,]+)/;

  let currentItem = null;

  for (let line of lines) {
    const cleanLine = line.replace(/^\|/, '').trim();
    const match = cleanLine.match(rowPattern);

    if (match) {
      if (currentItem) {
        products.push(currentItem);
      }
      
      const costPrice = parseFloat(match[3].replace(/\s/g, '').replace(',', '.'));
      const totalAmount = parseFloat(match[6].replace(/\s/g, '').replace(',', '.'));

      currentItem = {
        id: parseInt(match[1], 10),
        title: match[2].trim(),
        cost_price: costPrice, // Себестоимость из колонки "Цена"
        quantity: parseInt(match[4], 10),
        unit: match[5] || 'шт',
        total_sum: totalAmount
      };
    } else if (currentItem) {
      // Если строка не содержит структуру таблицы, но идет следом — это продолжение названия товара
      if (!line.includes('Итого') && !line.includes('ЗАКАЗ №') && !line.includes('Заказчик') && !line.includes('Наименование')) {
        if (!line.startsWith('|')) {
          currentItem.title += ' ' + line.trim();
        }
      }
    }
  }

  if (currentItem) {
    products.push(currentItem);
  }

  return products;
}
