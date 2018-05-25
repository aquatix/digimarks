var options = {};
var elem = document.querySelector(".sidenav");
var instance = M.Sidenav.init(elem, options);

elem = document.querySelector(".collapsible");
instance = M.Collapsible.init(elem, {
    // inDuration: 1000,
    // outDuration: 1000
});
