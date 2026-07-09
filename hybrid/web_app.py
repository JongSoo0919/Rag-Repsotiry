import logging
from html import escape

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from hybrid.query import hybrid_answer


app = FastAPI(title="Hybrid RAG (Vector→Graph) PoC")


def render_page(question="", answer="", vector_docs=None, entities=None, relationships=None, error=""):
    vector_docs = vector_docs or []
    entities = entities or []
    relationships = relationships or []

    vector_items = []
    for document in vector_docs:
        section = document.metadata.get("section", "(section 없음)")
        vector_items.append(f"<li><code>{escape(section)}</code></li>")

    entity_items = []
    for entity in entities:
        entity_items.append(
            f"""
            <li>
              <strong>{escape(entity["id"])}</strong>
              <span>{escape(entity.get("description") or "")}</span>
            </li>
            """
        )

    relation_items = []
    for relationship in relationships:
        relation_items.append(
            f"""
            <li>
              <code>{escape(relationship["source"])}</code>
              <span>--[{escape(relationship["relation"])}]--&gt;</span>
              <code>{escape(relationship["target"])}</code>
              <p>{escape(relationship.get("description") or "")}</p>
            </li>
            """
        )

    return f"""
    <!doctype html>
    <html lang="ko">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Hybrid RAG (Vector→Graph) PoC</title>
        <style>
          body {{
            margin: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            background: #f6f7f9;
            color: #1f2933;
          }}
          main {{
            width: min(960px, calc(100% - 32px));
            margin: 40px auto;
          }}
          h1 {{
            margin: 0 0 8px;
            font-size: 28px;
          }}
          .meta {{
            margin: 0 0 24px;
            color: #5f6b7a;
            font-size: 14px;
          }}
          form {{
            display: grid;
            gap: 12px;
            margin-bottom: 24px;
          }}
          textarea {{
            width: 100%;
            min-height: 110px;
            box-sizing: border-box;
            padding: 14px;
            border: 1px solid #c8d0d9;
            border-radius: 8px;
            font: inherit;
            resize: vertical;
            background: white;
          }}
          button {{
            width: fit-content;
            padding: 10px 16px;
            border: 0;
            border-radius: 8px;
            background: #256f5b;
            color: white;
            font-weight: 700;
            cursor: pointer;
          }}
          section {{
            background: white;
            border: 1px solid #d9e0e8;
            border-radius: 8px;
            padding: 18px;
            margin-bottom: 16px;
          }}
          h2 {{
            margin: 0 0 12px;
            font-size: 18px;
          }}
          ul {{
            margin: 0;
            padding-left: 20px;
          }}
          li {{
            margin: 10px 0;
            line-height: 1.6;
          }}
          code {{
            background: #eef2f5;
            padding: 2px 5px;
            border-radius: 4px;
          }}
          p {{
            margin: 4px 0 0;
          }}
          .answer {{
            white-space: pre-wrap;
            line-height: 1.7;
          }}
          .error {{
            color: #b42318;
            white-space: pre-wrap;
          }}
        </style>
      </head>
      <body>
        <main>
          <h1>Hybrid RAG (Vector→Graph) PoC</h1>
          <p class="meta">흐름: Vector 검색 → Graph 시드/확장 → 종합 답변</p>

          <form method="post" action="/ask">
            <textarea name="question" placeholder="예: Deployment를 외부 통신하려면 어떻게 해야해?">{escape(question)}</textarea>
            <button type="submit">질문하기</button>
          </form>

          {"<section><h2>오류</h2><div class='error'>" + escape(error) + "</div></section>" if error else ""}
          {"<section><h2>답변</h2><div class='answer'>" + escape(answer) + "</div></section>" if answer else ""}
          {"<section><h2>Vector 검색 청크</h2><ul>" + "".join(vector_items) + "</ul></section>" if vector_docs else ""}
          {"<section><h2>관련 Entity</h2><ul>" + "".join(entity_items) + "</ul></section>" if entities else ""}
          {"<section><h2>그래프 관계</h2><ul>" + "".join(relation_items) + "</ul></section>" if relationships else ""}
        </main>
      </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
def index():
    return render_page()


@app.post("/ask", response_class=HTMLResponse)
def ask(question: str = Form(...)):
    try:
        vector_docs, entities, relationships, answer = hybrid_answer(question)
        return render_page(
            question=question,
            answer=answer,
            vector_docs=vector_docs,
            entities=entities,
            relationships=relationships,
        )
    except Exception:
        logging.exception("hybrid_answer failed")
        return render_page(question=question, error="요청 처리 중 오류가 발생했습니다.")
