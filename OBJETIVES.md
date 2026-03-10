First Core idea: Build a CV template
Format: Reverse-chronological, one page (max two if 10+ years experience). This is the most widely recognized and ATS-friendly format, and it's what recruiters and hiring managers expect to see. Jofibocom It puts your most recent role at the top and shows career progression clearly.
Key principles that matter in tech specifically:
Quantify impact, not responsibilities. Hiring managers aren't looking for a list of tasks — they want to know how you've contributed, what you've achieved, and why you're worth investing in. Flexa Instead of "Worked on computer vision pipeline," write "Reduced inference latency by 40% on edge devices, enabling real-time detection at 30fps." With your CV/embedded background, you likely have great metrics to highlight.
Clean, minimal design. Layouts that include emojis, graphics, or unusual fonts are often filtered out or cause parsing issues with ATS systems. Toptal This is why LaTeX CVs are so popular in tech — they produce clean, consistent PDFs with no visual noise. The classic moderncv or altacv LaTeX templates are widely respected.
Skills section matters, but show context. A list of programming languages, tools, and frameworks isn't enough anymore. Flexa Show how you used them. For you: Python, C++, OpenCV, embedded Linux, etc. — but tied to projects and results.
Include links. Directly linking to LinkedIn and online portfolio lets hiring managers get a fuller picture of your qualifications. ResumeBuilder.com GitHub, personal site, and LinkedIn are standard in tech CVs.
The "gold standard" in practice for software/CV engineers is a LaTeX-generated PDF using something like Jake's Resume template, moderncv, or altacv — one page, reverse-chronological, no photo (especially for US/UK markets), heavy on quantified achievements, with a clean skills section and links to GitHub/portfolio.
Your objetive: Create this reference CV

Second The Core Idea: A CI/CD pipeline that parses your LaTeX CV, extracts structured data, and generates a static HTML page — all triggered automatically when you push changes to your CV repo.
Architecture:
1. Single GitHub repo with this structure:
my-site/
├── cv/
│   └── cv.tex
├── templates/
│   └── index.html.j2    (Jinja2 template)
├── scripts/
│   └── build.py
├── docs/               (generated output, served by GitHub Pages)
│   └── index.html
└── .github/
    └── workflows/
        └── build.yml
2. The build pipeline (GitHub Actions workflow):
When you git push changes to cv.tex, the workflow triggers and does three things in sequence:
Step A — Parse the LaTeX. A Python script reads your cv.tex and extracts structured data: name, bio, work experience, education, projects, links, skills, etc. You have two options here. The straightforward one is regex/string parsing — LaTeX is structured enough (sections, \item, custom commands) that you can parse it reliably, especially if you control the template and use consistent commands like \cventry{}, \project{}, etc. The other option is using a library like pylatexenc or TexSoup which give you an AST-like representation of the .tex file. I'd recommend designing your CV with parsing in mind — define custom LaTeX commands that are easy to extract, like \role{title}{company}{dates}{description}.
Step B — Render HTML. Take the extracted data (as a Python dict or JSON) and feed it into a Jinja2 HTML template. This template is your Karpathy-style page — clean, minimal, single file with inline CSS. Jinja2 is perfect because it keeps the design completely separate from the data. You style it once and forget about it.
Step C — Output to docs/. Write the rendered index.html to the docs/ folder, which GitHub Pages serves directly. The workflow commits and pushes this generated file back to the repo.
3. Hosting: GitHub Pages, configured to serve from the docs/ folder on main branch. Add a custom domain via CNAME if you want.
Why this approach:

Single source of truth — your CV .tex file is the only thing you ever edit. The website updates itself.
No external services — everything runs inside GitHub Actions, for free.
No JavaScript frameworks — the output is a single static HTML file, just like Karpathy's.
Fully reproducible — anyone who clones your repo can build the site locally with python scripts/build.py.
LaTeX still works — you can still compile cv.tex to PDF as usual for the "formal" version. You could even have the pipeline generate the PDF too and host it on the same page as a download link.

One key design decision: Structure your .tex file with custom commands that serve as both good LaTeX formatting and easy parse targets. For example, instead of freeform LaTeX, use something like:
latex\newcommand{\experience}[4]{...}  % {title}{company}{dates}{description}
\experience{CV Engineer}{Tesla}{2020-2023}{Led computer vision team...}
This way the same source compiles to a beautiful PDF and is trivially parseable by your Python script.
Optional enhancements for later: You could add the PDF compilation step to the same pipeline (install texlive in the GitHub Action), so pushing to the repo generates both the website and a fresh PDF download link. You could also add a CNAME file for a custom domain.
You need to construct this full pipeline — the build script, the Jinja2 template, and the GitHub Actions workflow instructive.

