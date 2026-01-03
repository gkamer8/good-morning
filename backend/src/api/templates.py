"""Shared HTML templates and styles for the Morning Drive website."""

# Common CSS styles used across all pages
COMMON_STYLES = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: #f5f7fa;
        min-height: 100vh;
        line-height: 1.6;
        color: #333;
    }
    .header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px 40px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .header h1 { font-size: 1.5rem; }
    .header a {
        color: white;
        text-decoration: none;
        opacity: 0.9;
    }
    .header a:hover { opacity: 1; }
    .nav {
        display: flex;
        gap: 24px;
        align-items: center;
    }
    .nav a {
        color: rgba(255,255,255,0.85);
        text-decoration: none;
        font-weight: 500;
        transition: all 0.2s;
        padding: 6px 12px;
        border-radius: 6px;
    }
    .nav a:hover {
        color: white;
        background: rgba(255,255,255,0.15);
    }
    .nav a.active {
        color: white;
        background: rgba(255,255,255,0.2);
    }
    .container {
        max-width: 1000px;
        margin: 0 auto;
        padding: 40px 20px;
    }
    .card {
        background: white;
        border-radius: 12px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin-bottom: 30px;
        overflow: hidden;
    }
    .card-header {
        padding: 20px 24px;
        border-bottom: 1px solid #eee;
        font-weight: 600;
        font-size: 1.1rem;
    }
    .card-body { padding: 24px; }
    h2 { margin-bottom: 16px; color: #333; }
    h3 { margin: 24px 0 12px 0; color: #444; }
    p { margin-bottom: 12px; color: #555; }
    pre {
        background: #1e1e1e;
        color: #d4d4d4;
        padding: 16px;
        border-radius: 8px;
        overflow-x: auto;
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        font-size: 14px;
        margin: 12px 0;
    }
    code {
        background: #f0f0f0;
        padding: 2px 6px;
        border-radius: 4px;
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        font-size: 14px;
    }
    pre code {
        background: transparent;
        padding: 0;
    }
    ul, ol {
        margin: 12px 0 12px 24px;
    }
    li { margin-bottom: 8px; }
    a { color: #667eea; }
    a:hover { color: #764ba2; }
    .btn {
        display: inline-block;
        padding: 12px 24px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 8px;
        font-size: 16px;
        font-weight: 600;
        text-decoration: none;
        cursor: pointer;
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        color: white;
    }
    .btn-secondary {
        background: #6c757d;
    }
    .btn-secondary:hover {
        box-shadow: 0 4px 12px rgba(108, 117, 125, 0.4);
    }
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 16px 0;
    }
    th, td {
        padding: 12px 16px;
        text-align: left;
        border-bottom: 1px solid #eee;
    }
    th {
        background: #f8f9fa;
        font-weight: 600;
        font-size: 0.9rem;
        color: #666;
    }
    .hero {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 80px 40px;
        text-align: center;
    }
    .hero h1 {
        font-size: 3rem;
        margin-bottom: 16px;
    }
    .hero p {
        font-size: 1.3rem;
        opacity: 0.9;
        margin-bottom: 32px;
        color: white;
    }
    .hero .btn {
        background: white;
        color: #667eea;
        margin: 0 8px;
    }
    .hero .btn:hover {
        color: #764ba2;
    }
    .features {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 24px;
        margin: 40px 0;
    }
    .feature {
        background: white;
        border-radius: 12px;
        padding: 24px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    .feature h3 {
        margin: 0 0 12px 0;
        color: #667eea;
    }
    .feature p {
        margin: 0;
        font-size: 0.95rem;
    }
    .sidebar-nav {
        background: white;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin-bottom: 24px;
    }
    .sidebar-nav h4 {
        font-size: 0.85rem;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 12px;
    }
    .sidebar-nav a {
        display: block;
        padding: 8px 12px;
        color: #333;
        text-decoration: none;
        border-radius: 6px;
        margin-bottom: 4px;
    }
    .sidebar-nav a:hover {
        background: #f0f0f0;
    }
    .sidebar-nav a.active {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }
    .docs-layout {
        display: grid;
        grid-template-columns: 220px 1fr;
        gap: 32px;
        max-width: 1200px;
        margin: 0 auto;
        padding: 40px 20px;
    }
    @media (max-width: 768px) {
        .docs-layout {
            grid-template-columns: 1fr;
        }
        .hero h1 { font-size: 2rem; }
        .hero p { font-size: 1rem; }
    }
    .note {
        background: #e8f4fd;
        border-left: 4px solid #667eea;
        padding: 16px;
        border-radius: 0 8px 8px 0;
        margin: 16px 0;
    }
    .warning {
        background: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 16px;
        border-radius: 0 8px 8px 0;
        margin: 16px 0;
    }
    .footer {
        background: #1e1e1e;
        color: #999;
        text-align: center;
        padding: 40px 20px;
        margin-top: 60px;
    }
    .footer a { color: #667eea; }
"""


def base_page(title: str, content: str, active_page: str = "") -> str:
    """Generate a base HTML page with header navigation."""
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Morning Drive</title>
    <style>{COMMON_STYLES}</style>
</head>
<body>
    <div class="header">
        <a href="/"><h1>Morning Drive</h1></a>
        <nav class="nav">
            <a href="/docs/getting-started" class="{'active' if active_page == 'docs' else ''}">Docs</a>
            <a href="/api/docs">API</a>
            <a href="/admin">Admin</a>
        </nav>
    </div>
    {content}
    <div class="footer">
        <p>Morning Drive - AI-powered personalized morning briefings</p>
        <p><a href="https://github.com/gkamer8/good-morning">View on GitHub</a></p>
    </div>
</body>
</html>
"""


def docs_page(title: str, content: str, active_doc: str = "") -> str:
    """Generate a documentation page with sidebar navigation."""
    sidebar = f"""
    <div class="sidebar">
        <div class="sidebar-nav">
            <h4>Documentation</h4>
            <a href="/docs/getting-started" class="{'active' if active_doc == 'getting-started' else ''}">Getting Started</a>
            <a href="/docs/deployment" class="{'active' if active_doc == 'deployment' else ''}">Deployment</a>
            <a href="/docs/development" class="{'active' if active_doc == 'development' else ''}">Development</a>
            <a href="/docs/api-reference" class="{'active' if active_doc == 'api-reference' else ''}">API Reference</a>
        </div>
    </div>
    """

    body = f"""
    <div class="docs-layout">
        {sidebar}
        <main>
            <div class="card">
                <div class="card-body">
                    <h2>{title}</h2>
                    {content}
                </div>
            </div>
        </main>
    </div>
    """

    return base_page(title, body, active_page="docs")
