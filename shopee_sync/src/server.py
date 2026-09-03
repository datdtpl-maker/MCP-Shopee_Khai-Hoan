import json
import logging
from typing import Optional, List, Dict, Any
from mcp.server.fastmcp import FastMCP
from .discovery_cache import CachedFastMCPMixin

# Import modules nội bộ
from . import config
from . import auth
from . import shopee_client
from . import notion_to_bigseller


# Thiết lập logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("shopee_mcp_server")

# Khởi tạo FastMCP Server
class ShopeeFastMCP(CachedFastMCPMixin, FastMCP):
    def __init__(self, *args, **kwargs):
        # Keep metadata caching bounded and invalidate on registry changes.
        ttl_seconds = kwargs.pop("discovery_ttl_seconds", 60.0)
        super().__init__(*args, **kwargs)
        self._init_discovery_cache(ttl_seconds)


mcp = ShopeeFastMCP(
    name="Shopee-MCP-Server",
    instructions="MCP Server cung cấp bộ công cụ kết nối Shopee API V2 để đăng và quản lý sản phẩm."
)

@mcp.tool()
def shopee_get_auth_url() -> str:
    """
    Sinh đường dẫn (URL) đăng nhập ủy quyền của Shopee.
    Shop owner cần truy cập link này bằng trình duyệt để đăng nhập tài khoản bán hàng Shopee và phê duyệt ứng dụng.
    Sau khi phê duyệt, Shopee sẽ chuyển hướng về REDIRECT_URL kèm theo tham số 'code' (Authorization Code).
    
    Returns:
        str: Chuỗi URL cấp quyền.
    """
    try:
        url = auth.get_auth_url()
        return json.dumps({
            "status": "success",
            "auth_url": url,
            "instructions": "Vui lòng copy URL này dán vào trình duyệt, đăng nhập shop Shopee và đồng ý cấp quyền. Sau đó copy giá trị 'code' từ thanh địa chỉ để dùng cho tool shopee_get_tokens."
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@mcp.tool()
def shopee_get_tokens(auth_code: str, shop_id: Optional[int] = None) -> str:
    """
    Đổi mã ủy quyền (Authorization Code) lấy cặp access_token và refresh_token từ Shopee.
    Cặp token này sẽ được lưu tự động vào file tokens.json để dùng cho các request tiếp theo.

    Args:
        auth_code (str): Mã code nhận được sau khi shop owner đồng ý ủy quyền từ redirect URL.
        shop_id (Optional[int]): ID của shop Shopee cần kết nối. Nếu bỏ trống sẽ dùng SHOP_ID cấu hình trong file .env.

    Returns:
        str: Kết quả JSON thông báo trạng thái nhận token.
    """
    try:
        res = auth.fetch_tokens(auth_code, shop_id)
        return json.dumps({
            "status": "success",
            "message": "Đã lấy và lưu tokens thành công.",
            "data": {
                "access_token_prefix": res.get("access_token", "")[:10] + "...",
                "expires_in": res.get("expires_in"),
                "shop_id": shop_id or config.SHOP_ID
            }
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@mcp.tool()
def shopee_refresh_token() -> str:
    """
    Thực hiện làm mới (refresh) access_token bằng refresh_token hiện có.
    Access token của Shopee chỉ sống trong 4 giờ. Server tự động gọi hàm này trước mỗi request,
    nhưng bạn có thể gọi thủ công qua tool này để kiểm tra hoặc cập nhật sớm.

    Returns:
        str: Kết quả JSON về việc refresh token.
    """
    try:
        res = auth.refresh_token()
        return json.dumps({
            "status": "success",
            "message": "Làm mới token thành công.",
            "expires_in": res.get("expires_in")
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@mcp.tool()
def shopee_get_logistic_channels() -> str:
    """
    Lấy danh sách các đơn vị vận chuyển (Logistic Channels) được kích hoạt cho gian hàng Shopee này.
    Bạn bắt buộc phải chọn một hoặc nhiều ID đơn vị vận chuyển hợp lệ (enabled = True) khi đăng sản phẩm.

    Returns:
        str: Chuỗi JSON chứa danh sách các đơn vị vận chuyển.
    """
    try:
        channels = shopee_client.get_logistic_channels()
        return json.dumps({
            "status": "success",
            "channels": channels
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@mcp.tool()
def shopee_get_categories(language: str = "vi") -> str:
    """
    Lấy toàn bộ danh sách ngành hàng (Categories) từ Shopee.
    Hãy sử dụng danh sách này để tìm kiếm và xác định đúng 'category_id' cho sản phẩm cần đăng.

    Args:
        language (str): Ngôn ngữ của tên danh mục. Mặc định là 'vi' (Tiếng Việt).

    Returns:
        str: Chuỗi JSON danh sách ngành hàng.
    """
    try:
        categories = shopee_client.get_categories(language)
        return json.dumps({
            "status": "success",
            "categories": categories
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@mcp.tool()
def shopee_get_attributes(category_id: int, language: str = "vi") -> str:
    """
    Lấy thông tin các thuộc tính (Attributes) của ngành hàng đã chọn (ví dụ: thương hiệu, xuất xứ, chất liệu...).
    Đặc biệt lưu ý các thuộc tính có 'is_mandatory = true' vì đó là những thuộc tính bắt buộc phải điền khi đăng sản phẩm.

    Args:
        category_id (int): ID ngành hàng Shopee (category_id).
        language (str): Ngôn ngữ phản hồi. Mặc định là 'vi'.

    Returns:
        str: Chuỗi JSON danh sách thuộc tính và các giá trị đi kèm.
    """
    try:
        attributes = shopee_client.get_attributes(category_id, language)
        return json.dumps({
            "status": "success",
            "attributes": attributes
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@mcp.tool()
def shopee_upload_image(file_path_or_url: str) -> str:
    """
    Tải ảnh từ máy tính cục bộ hoặc từ một đường dẫn URL internet lên hệ thống Shopee CDN.
    Shopee bắt buộc ảnh sản phẩm phải được tải lên CDN của họ và lấy về 'image_id' trước khi đăng sản phẩm.

    Args:
        file_path_or_url (str): Đường dẫn file ảnh cục bộ (ví dụ: 'C:/anh/sanpham.png') hoặc một URL ảnh trên web (ví dụ: 'https://example.com/image.jpg').

    Returns:
        str: Chuỗi JSON chứa 'image_id' và 'image_url' trên CDN của Shopee.
    """
    try:
        res = shopee_client.upload_image(file_path_or_url)
        return json.dumps({
            "status": "success",
            "image_id": res.get("image_id"),
            "image_url": res.get("image_url")
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@mcp.tool()
def shopee_add_product(
    item_name: str,
    description: str,
    original_price: float,
    normal_stock: int,
    category_id: int,
    image_id_list: List[str],
    weight: float,
    package_length: int = 10,
    package_width: int = 10,
    package_height: int = 10,
    logistic_ids: Optional[List[int]] = None,
    brand_name: str = "No Brand",
    attributes: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Đăng sản phẩm mới lên gian hàng Shopee.

    Args:
        item_name (str): Tên sản phẩm (Giới hạn ký tự từ Shopee, thường từ 20 đến 120 ký tự).
        description (str): Mô tả chi tiết về sản phẩm (Tối thiểu 100 ký tự theo chuẩn Shopee).
        original_price (float): Giá gốc sản phẩm (Bằng Việt Nam Đồng, ví dụ: 150000.0).
        normal_stock (int): Số lượng tồn kho ban đầu (ví dụ: 100).
        category_id (int): ID danh mục sản phẩm (Lấy từ tool shopee_get_categories).
        image_id_list (List[str]): Danh sách các ID ảnh sản phẩm đã upload (Lấy từ tool shopee_upload_image). Tối thiểu 1 ảnh.
        weight (float): Khối lượng sản phẩm sau đóng gói tính bằng kilogram (kg) (ví dụ: 0.25 cho 250 gram).
        package_length (int): Chiều dài gói hàng sau đóng gói (cm). Mặc định là 10.
        package_width (int): Chiều rộng gói hàng sau đóng gói (cm). Mặc định là 10.
        package_height (int): Chiều cao gói hàng sau đóng gói (cm). Mặc định là 10.
        logistic_ids (Optional[List[int]]): Danh sách các ID đơn vị vận chuyển hỗ trợ cho sản phẩm này. Nếu bỏ trống, hệ thống sẽ tự động cấu hình bằng tất cả đơn vị vận chuyển đang bật trên Shop.
        brand_name (str): Tên thương hiệu. Mặc định là 'No Brand' (Thương hiệu tự do).
        attributes (Optional[List[Dict[str, Any]]]): Danh sách các thuộc tính sản phẩm bổ sung. 
                                                     Định dạng: [{"attribute_id": 123, "attribute_value_list": [{"value_id": 456}]}] hoặc text.

    Returns:
        str: Chuỗi JSON kết quả đăng sản phẩm bao gồm 'item_id' của sản phẩm mới tạo.
    """
    try:
        res = shopee_client.add_product(
            item_name=item_name,
            description=description,
            original_price=original_price,
            normal_stock=normal_stock,
            category_id=category_id,
            image_id_list=image_id_list,
            weight=weight,
            package_length=package_length,
            package_width=package_width,
            package_height=package_height,
            logistic_ids=logistic_ids,
            brand_name=brand_name,
            attributes=attributes
        )
        return json.dumps({
            "status": "success",
            "message": res.get("message", "Đăng sản phẩm thành công."),
            "item_id": res.get("item_id"),
            "data": res
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

@mcp.tool()
def shopee_convert_notion_to_bigseller_excel(notion_url: str, output_excel_path: Optional[str] = None) -> str:
    """
    Đọc dữ liệu từ link trang Notion công khai và xuất ra file Excel chuẩn mẫu Import của BigSeller.
    Công cụ này sẽ tự động tải dữ liệu văn bản để làm tên/mô tả sản phẩm và trích xuất các đường link hình ảnh.

    Args:
        notion_url (str): Link trang Notion công khai (Share to web) chứa thông tin sản phẩm.
        output_excel_path (Optional[str]): Đường dẫn nơi lưu file Excel kết quả. Nếu bỏ trống, file sẽ lưu tại thư mục 'output' của dự án.

    Returns:
        str: Chuỗi JSON chứa đường dẫn tới file Excel kết quả và dữ liệu thô đã chuyển đổi.
    """
    try:
        data = notion_to_bigseller.parse_notion_public_page(notion_url)
        
        # Xác định đường dẫn output
        if not output_excel_path:
            output_dir = config.TOKEN_FILE_PATH.parent / "output"
            output_dir.mkdir(exist_ok=True)
            output_excel_path = str(output_dir / "bigseller_products.xlsx")
            
        notion_to_bigseller.export_to_bigseller_excel([data], output_excel_path)
        
        return json.dumps({
            "status": "success",
            "message": "Chuyển đổi dữ liệu Notion sang file Excel BigSeller thành công.",
            "output_file": output_excel_path,
            "product_extracted": {
                "title": data["title"],
                "images_found": len(data["image_urls"]),
                "description_preview": data["description"][:100] + "..." if len(data["description"]) > 100 else data["description"]
            }
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

if __name__ == "__main__":
    # Khởi chạy FastMCP Server qua kênh stdio (mặc định cho MCP integration)
    mcp.run()

