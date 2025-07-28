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
    return f"<style>" + "@import url('data:text/css;base64," + encoded + "');" + "</style>"


def generate_obfuscated_js() -> str:
    """Return a small script encoded in base64 to hide intent."""
    script = (
        "(function(){console.log('loading');})();"
    )
    encoded = base64.b64encode(script.encode()).decode()
    return (
        "<script>" "eval(atob('" + encoded + "'))" "</script>"
    )


def generate_fingerprinting_script() -> str:
    """Return a heavier JS snippet that collects extensive browser details."""
    var_names = [
        "".join(random.choices(string.ascii_lowercase, k=6)) for _ in range(10)
    ]
    (
        ua,
        res,
        depth,
        lang,
        plat,
        tz,
        cores,
        plugins_var,
        fonts_var,
        out,
    ) = var_names

    script = (
        f"var {ua}=navigator.userAgent;"
        f"var {res}=screen.width+'x'+screen.height;"
        f"var {depth}=screen.colorDepth;"
        f"var {lang}=navigator.language||'';"
        f"var {plat}=navigator.platform||'';"
        f"var {tz}=new Date().getTimezoneOffset();"
        f"var {cores}=navigator.hardwareConcurrency||0;"
        f"var {plugins_var}=[];"
        f"for(var i=0;i<(navigator.plugins||[]).length;i++){{{plugins_var}.push(navigator.plugins[i].name);}}"
        f"var {fonts_var}=[];"
        f"if(document.fonts&&document.fonts.forEach){{document.fonts.forEach(function(f){{{fonts_var}.push(f.family);}});}}"
        f"var {out}=[{ua},{res},{depth},{lang},{plat},{tz},{cores},{plugins_var}.join(','),{fonts_var}.join(',')];"
        "console.log('fp'," + out + ");"
    )
    return f"<script>{script}</script>"
