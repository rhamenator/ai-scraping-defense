(function(){
  var script=document.createElement('script');
  script.src='https://cdn.jsdelivr.net/npm/@fingerprintjs/fingerprintjs@3/dist/fp.min.js';
  script.async=true;
  script.onload=function(){
    FingerprintJS.load().then(function(fp){
      return fp.get();
    }).then(function(result){
      var id=result.visitorId;
      var secure=window.location.protocol==='https:' ? '; Secure' : '';
      document.cookie='fp_id='+id+'; path=/; SameSite=Strict'+secure;
    });
  };
  document.head.appendChild(script);
})();
