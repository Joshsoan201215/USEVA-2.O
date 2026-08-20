function toggleSidebar(){document.getElementById('sidebar').classList.toggle('open')}
function openModal(){document.getElementById('addModal').classList.add('open')}
function closeModal(){document.getElementById('addModal').classList.remove('open')}
const USEVA_LOCATIONS=['Pantry','Fridge','Cupboards','Freezer','Counter','Other'];
function locationOptionsHtml(selected){return USEVA_LOCATIONS.map(x=>`<option value="${esc(x)}" ${x===(selected||'Pantry')?'selected':''}>${esc(x)}</option>`).join('')}
function categoryOptionsHtml(selected){const base=['Produce','Dairy','Meat','Bakery','Beverages','Snacks','Frozen','Pantry','Other'];return [...new Set(base)].map(c=>`<option value="${c}" ${c===selected?'selected':''}>${c}</option>`).join('')}
function showManual(){
  document.querySelector('.modal-card').innerHTML=`<button class="modal-close" onclick="closeModal()">×</button>
  <div class="eyebrow">MANUAL ENTRY</div><h2>Add pantry item</h2><p class="muted">Category is suggested automatically. You can change it or create your own category.</p>
  <form action="/add-item" method="post" enctype="multipart/form-data" class="form-grid modal-form" style="grid-template-columns:1fr 1fr;margin-top:20px">
  <label>Name<input id="manualItemName" name="name" required placeholder="Milk" oninput="suggestManualCategory()"></label>
  <label>Category<select id="manualCategory" name="category" onchange="manualCategoryChanged()">${categoryOptionsHtml('')}</select></label>
  <div id="manualCustomCategoryWrap" class="custom-category-wrap hidden" style="grid-column:1/-1"><label>Custom category name<input id="manualCustomCategory" name="custom_category" placeholder="e.g. Frozen Foods"></label></div>
  <label>Quantity<input name="quantity" type="number" step="0.1" min="0.1" value="1"></label><label>Unit<input name="unit" value="unit"></label>
  <label>Price (₹)<input name="price" type="number" step="0.01" min="0" value="0"></label><label>Location<select name="location">${locationOptionsHtml('Pantry')}</select></label>
  <label>Purchase date<input id="manualPurchaseDate" name="purchase_date" type="date" value="${new Date().toISOString().slice(0,10)}" onchange="suggestManualExpiry()"></label><label>Expiry date<input id="manualExpiryDate" name="expiry_date" type="date"></label>
  <div id="manualExpiryHint" class="expiry-suggestion" style="grid-column:1/-1"><button type="button" class="secondary-btn" onclick="suggestManualExpiry()">✨ Suggest approximate expiry</button><span class="muted">Check package/manufacturer date when available.</span></div>
  <label style="grid-column:1/-1">Notes<input name="notes" placeholder="Optional notes"></label>
  <label style="grid-column:1/-1">Image<input name="image" type="file" accept="image/*"></label>
  <button class="primary-btn" type="submit" style="grid-column:1/-1">Add to pantry</button></form>`;
  fetch('/api/categories').then(r=>r.json()).then(d=>{if(d.ok){const select=document.getElementById('manualCategory');select.innerHTML=d.categories.map(c=>`<option value="${esc(c)}">${esc(c)}</option>`).join('');select.value='';}}).catch(()=>{});
}
function manualCategoryChanged(){const select=document.getElementById('manualCategory'),wrap=document.getElementById('manualCustomCategoryWrap'),input=document.getElementById('manualCustomCategory');if(select.value==='Other'){select.dataset.manual='1';wrap.classList.remove('hidden');input.focus()}else{select.dataset.manual='1';wrap.classList.add('hidden');input.value=''}}
async function suggestManualExpiry(){const name=document.getElementById('manualItemName')?.value.trim(),purchase=document.getElementById('manualPurchaseDate')?.value,out=document.getElementById('manualExpiryHint'),expiry=document.getElementById('manualExpiryDate');if(!name||!out)return;try{const r=await fetch('/api/estimate-expiry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,purchase_date:purchase})}),d=await r.json();if(d.available){expiry.value=d.expiry_date;out.innerHTML=`<span class="muted">Approx. ${d.min_date} to ${d.max_date} · suggested ${d.expiry_date}. ${esc(d.note)}</span>`}else out.innerHTML=`<span class="muted">${esc(d.message||'Check the package/manufacturer date.')}</span>`}catch(e){out.innerHTML='<span class="muted">Could not calculate estimate.</span>'}}
function editCategoryChanged(){const select=document.getElementById('editCategory'),wrap=document.getElementById('editCustomCategoryWrap');if(select.value==='Other')wrap.classList.remove('hidden');else{wrap.classList.add('hidden');document.getElementById('editCustomCategory').value=''}}
async function loadCategoryOptions(selected){try{const r=await fetch('/api/categories');const d=await r.json();if(d.ok){const select=document.getElementById('editCategory');select.innerHTML=d.categories.map(c=>`<option value="${esc(c)}" ${c===selected?'selected':''}>${esc(c)}</option>`).join('');}}catch(e){}}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function openEditItem(id,name,quantity,unit,price,purchaseDate,expiryDate,location,notes,category){
  openModal();
  document.querySelector('.modal-card').innerHTML=`<button class="modal-close" onclick="closeModal()">×</button>
  <div class="eyebrow">PANTRY ITEM</div><h2>Edit item</h2><p class="muted">Edit every pantry detail, including location and expiry.</p>
  <div class="form-grid modal-form" style="grid-template-columns:1fr 1fr;margin-top:20px">
   <label>Name<input id="editName" value="${esc(name)}"></label>
   <label>Category<select id="editCategory" onchange="editCategoryChanged()"></select></label>
   <div id="editCustomCategoryWrap" class="custom-category-wrap ${category==='Other'?'':'hidden'}" style="grid-column:1/-1"><label>Custom category name<input id="editCustomCategory" placeholder="e.g. Frozen Foods"></label></div>
   <label>Quantity<input id="editQuantity" type="number" step="0.1" min="0.1" value="${Number(quantity||1)}"></label>
   <label>Unit<input id="editUnit" value="${esc(unit||'unit')}"></label>
   <label>Price (₹)<input id="editPrice" type="number" step="0.01" min="0" value="${Number(price||0)}"></label>
   <label>Location<select id="editLocation">${locationOptionsHtml(location||'Pantry')}</select></label>
   <label>Purchase date<input id="editPurchaseDate" type="date" value="${purchaseDate||''}"></label>
   <label>Expiry date<input id="editExpiryDate" type="date" value="${expiryDate||''}"></label>
   <div id="editExpiryHint" class="expiry-suggestion" style="grid-column:1/-1"><button type="button" class="secondary-btn" onclick="suggestEditExpiry()">✨ Suggest approximate expiry</button><span class="muted">Check package/manufacturer date when available.</span></div>
   <label style="grid-column:1/-1">Notes<input id="editNotes" value="${esc(notes||'')}"></label>
   <button class="primary-btn" style="grid-column:1/-1" onclick="saveEditedPantryItem(${id})">Save changes</button>
  </div>`;
  loadCategoryOptions(category);
}
async function suggestEditExpiry(){const name=document.getElementById('editName')?.value.trim(),purchase=document.getElementById('editPurchaseDate')?.value,out=document.getElementById('editExpiryHint'),expiry=document.getElementById('editExpiryDate');if(!name)return;try{const r=await fetch('/api/estimate-expiry',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,purchase_date:purchase})}),d=await r.json();if(d.available){expiry.value=d.expiry_date;out.innerHTML=`<span class="muted">Approx. ${d.min_date} to ${d.max_date} · suggested ${d.expiry_date}. ${esc(d.note)}</span>`}else out.innerHTML=`<span class="muted">${esc(d.message||'Check the package/manufacturer date.')}</span>`}catch(e){out.innerHTML='<span class="muted">Could not calculate estimate.</span>'}}
async function saveEditedPantryItem(id){const payload={name:document.getElementById('editName').value.trim(),quantity:document.getElementById('editQuantity').value,unit:document.getElementById('editUnit').value,price:document.getElementById('editPrice').value,location:document.getElementById('editLocation').value,notes:document.getElementById('editNotes').value,purchase_date:document.getElementById('editPurchaseDate').value,expiry_date:document.getElementById('editExpiryDate').value,category:document.getElementById('editCategory').value,custom_category:document.getElementById('editCustomCategory')?.value.trim()||''};const r=await fetch(`/api/item/${id}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),d=await r.json();if(d.ok){closeModal();location.reload()}else alert(d.error||'Could not save changes')}
async function itemAction(url,btn,action,available,unit){if(!action){btn.disabled=true;const r=await fetch(url,{method:'POST'});if(r.ok)location.reload();else btn.disabled=false;return}openModal();const verb=action==='consume'?'consumed':'wasted';document.querySelector('.modal-card').innerHTML=`<button class="modal-close" onclick="closeModal()">×</button><div class="eyebrow">PANTRY UPDATE</div><h2>${action==='consume'?'Consume item':'Record waste'}</h2><p class="muted">Available: <strong>${Number(available||0)} ${esc(unit||'unit')}</strong></p><label class="quantity-action-label">Quantity to ${verb} :<input id="actionQuantity" type="number" min="0.1" max="${Number(available||0)}" step="0.1" value="${Number(available||0)}"></label><div class="quantity-action-buttons"><button class="secondary-btn" onclick="closeModal()">Cancel</button><button class="primary-btn" onclick="submitItemAction('${url}',${action==='consume'?"'consume'":"'waste'"})">${action==='consume'?'Consume':'Waste'}</button></div>`}
async function submitItemAction(url,action){const input=document.getElementById('actionQuantity'),quantity=Number(input?.value||0);if(!quantity||quantity<=0){alert('Enter a valid quantity.');return}const btn=document.querySelector('.quantity-action-buttons .primary-btn');btn.disabled=true;try{const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({quantity})}),d=await r.json();if(!d.ok)throw new Error(d.error||'Could not update item.');closeModal();location.reload()}catch(e){alert(e.message);btn.disabled=false}}
async function toggleShop(id,btn){const r=await fetch(`/shopping/${id}/toggle`,{method:'POST'});if(r.ok)location.reload()}
async function deleteShop(id,btn){const r=await fetch(`/shopping/${id}/delete`,{method:'POST'});if(r.ok)btn.closest('.shopping-row').remove()}
async function switchBranch(id){
  try{
    const r=await fetch('/api/branch/switch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({branch_id:Number(id)})});
    const d=await r.json();
    if(!r.ok || !d.ok) throw new Error(d.error||'Could not switch branch.');
    window.location.reload();
  }catch(e){alert(e.message||'Could not switch branch.');}
}
async function createBranch(){
  const name=prompt('Enter a new branch name (e.g. Home, Shop, Office, Hostel Kitchen):');
  if(name===null || !name.trim()) return;
  try{
    const r=await fetch('/api/branch/create',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({name:name.trim()})});
    const text=await r.text();
    let d={}; try{d=JSON.parse(text)}catch(e){throw new Error('Server returned an invalid response. Please restart USEVA and try again.');}
    if(!r.ok || !d.ok) throw new Error(d.error||'Could not create branch.');
    window.location.reload();
  }catch(e){alert('Branch creation failed: '+(e.message||'Unknown error'));}
}
async function clearCurrentBranch(){if(!confirm('Clear ALL pantry, receipts, shopping list and waste data for the current branch?'))return;if(!confirm('This cannot be undone. Clear the current branch now?'))return;const r=await fetch('/api/clear/current',{method:'POST'});const d=await r.json();alert(d.message||d.error||'Done');if(d.ok)location.reload()}
async function clearAllInventory(){if(!confirm('Clear ALL inventory data from EVERY branch? Branch accounts and categories will remain.'))return;if(!confirm('Final confirmation: permanently delete all pantry, receipt, shopping and waste records across all branches?'))return;const r=await fetch('/api/clear/all',{method:'POST'});const d=await r.json();alert(d.message||d.error||'Done');if(d.ok)location.reload()}
window.addEventListener('click',e=>{if(e.target.id==='addModal')closeModal()});
setTimeout(()=>document.querySelectorAll('.toast').forEach(x=>x.remove()),3500);
async function suggestManualCategory(){const input=document.getElementById('manualItemName'),select=document.getElementById('manualCategory');if(!input||!select||select.dataset.manual==='1')return;clearTimeout(window.manualCategoryTimer);window.manualCategoryTimer=setTimeout(async()=>{try{const r=await fetch('/api/suggest-category',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:input.value})});const d=await r.json();if(d.ok&&select.dataset.manual!=='1'){select.value=d.category;manualCategoryChanged()}}catch(e){}},300)}
