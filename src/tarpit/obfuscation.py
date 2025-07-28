import base64
import random
import string


def generate_obfuscated_css() -> str:
    """Return CSS encoded in base64 so it must be decoded before use."""
    css_rules = [
        "body{background:#fff;color:#111;}",
        "a{color:#06c;text-decoration:none;}",
        "a:hover{text-decoration:underline;}",
    ]
    css = "\n".join(css_rules)
    encoded = base64.b64encode(css.encode()).decode()
    return (
        "<style>" + "@import url('data:text/css;base64," + encoded + "');" + "</style>"
    )


def generate_obfuscated_js() -> str:
    """Return a small script that executes after decoding."""
    script = "(function(){console.log('loading');})();"
    encoded = base64.b64encode(script.encode()).decode()
    payload = (
        f"(function(d){{var s=d.createElement('script');"
        f"s.textContent=atob('{encoded}');d.head.appendChild(s);}})(document);"
    )
    return f"<script>{payload}</script>"


def generate_fingerprinting_script() -> str:
    """Return a script that captures detailed browser information."""
    names = ["".join(random.choices(string.ascii_lowercase, k=6)) for _ in range(14)]
    (
        ua,
        res,
        depth,
        lang,
        plat,
        tz,
        cores,
        mem,
        dnt,
        vendor,
        renderer,
        plugins_var,
        fonts_var,
        out_var,
    ) = names

    script = (
        f"var {ua}=navigator.userAgent;"
        f"var {res}=screen.width+'x'+screen.height;"
        f"var {depth}=screen.colorDepth;"
        f"var {lang}=navigator.language||'';"
        f"var {plat}=navigator.platform||'';"
        f"var {tz}=new Date().getTimezoneOffset();"
        f"var {cores}=navigator.hardwareConcurrency||0;"
        f"var {mem}=navigator.deviceMemory||0;"
        f"var {dnt}=navigator.doNotTrack||'';"
        f"var {vendor}=navigator.vendor||'';"
        f"var {plugins_var}=[];"
        f"for(var i=0;i<(navigator.plugins||[]).length;i++){{{plugins_var}.push(navigator.plugins[i].name);}}"
        f"var {fonts_var}=[];"
        f"if(document.fonts&&document.fonts.forEach){{document.fonts.forEach(function(f){{{fonts_var}.push(f.family);}});}}"
        f"var {renderer}='';"
        "try{var c=document.createElement('canvas');"
        "var g=c.getContext('webgl')||c.getContext('experimental-webgl');"
        "var e=g.getExtension('WEBGL_debug_renderer_info');"
        f"if(g&&e){{{renderer}=g.getParameter(e.UNMASKED_RENDERER_WEBGL);}}"
        "catch(t){}"
        f"var {out_var}=["
        f"{ua},{res},{depth},{lang},{plat},{tz},{cores},{mem},{dnt},{vendor},{renderer},"
        f"{plugins_var}.join(','),{fonts_var}.join(',')];"
        f"console.log('fp',{out_var});"
    )
    return f"<script>{script}</script>"
