(function(){
  var script=document.createElement('script');
  script.src='https://cdn.jsdelivr.net/npm/@fingerprintjs/fingerprintjs@3/dist/fp.min.js';
  script.async=true;
  script.onload=function(){
    FingerprintJS.load().then(function(fp){
      return fp.get();
    }).then(function(result){
      var id=result.visitorId;
      document.cookie='fp_id='+id+'; path=/; SameSite=Lax';
    });
  };
  document.head.appendChild(script);
})();
